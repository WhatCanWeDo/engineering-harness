"""Optional FastEmbed adapter. Only setup_model may download public model files."""
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

from .knowledge import encode, fail, sha

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
POLICY = "token-chunks96-mean-v1"


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def setup_model(output):
    from fastembed import TextEmbedding
    # Dependency installation is separate from model download.
    from huggingface_hub import HfApi, snapshot_download
    directory = Path(output).expanduser().absolute()
    if directory.exists():
        fail("output_exists", "Choose a new model bundle directory")
    description = next(m for m in TextEmbedding.list_supported_models() if m["model"] == MODEL)
    repo = description["sources"]["hf"]
    revision = HfApi().model_info(repo).sha
    directory.mkdir(parents=True, exist_ok=False)
    patterns = [description["model_file"], "*.json", "tokenizer.*", "vocab.*", "sentencepiece.bpe.model", *description["additional_files"]]
    # A bounded public model download; no project material is included in this call.
    snapshot_download(repo, revision=revision, allow_patterns=patterns, local_dir=directory / "files", max_workers=3)
    hashes = {str(p.relative_to(directory / "files")): file_hash(p)
              for p in sorted((directory / "files").rglob("*")) if p.is_file() and ".cache" not in p.parts}
    payload = {"version": 1, "model": MODEL, "dimensions": description["dim"], "repository": repo,
               "revision": revision, "files": hashes, "policy": POLICY,
               "fastembed_version": version("fastembed"), "onnxruntime_version": version("onnxruntime"),
               "license": description["license"]}
    with (directory / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
    provider = LocalEmbedder(directory)
    provider.embed(["Local model readiness probe"], kind="query")
    return {"status": "ready", "bundle": str(directory), "model_id": provider.model_id,
            "dimensions": provider.dimensions, "source_revision": revision}


class LocalEmbedder:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().absolute()
        manifest = json.loads((self.directory / "manifest.json").read_text())
        if (manifest.get("version") != 1 or manifest.get("model") != MODEL or
                manifest.get("dimensions") != 384 or manifest.get("policy") != POLICY):
            fail("model_bundle", "Unsupported local model bundle")
        if manifest["fastembed_version"] != version("fastembed") or manifest["onnxruntime_version"] != version("onnxruntime"):
            fail("model_bundle", "Runtime differs from bundle; prepare a new bundle/versioned index")
        files = manifest.get("files", {})
        if not isinstance(files, dict) or "tokenizer.json" not in files or "model_optimized.onnx" not in files:
            fail("model_bundle", "Incomplete model manifest")
        for name, digest in files.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                fail("model_bundle", "Invalid model file path")
            path = self.directory / "files" / relative
            if path.is_symlink() or file_hash(path) != digest:
                fail("model_bundle", "Model file digest mismatch")
        self.model_id = "fastembed:" + MODEL + ":" + sha(encode(manifest))
        self.dimensions = manifest["dimensions"]
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            # Both flags and a concrete local path prevent implicit downloads.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            from fastembed import TextEmbedding
            from tokenizers import Tokenizer
            self._model = TextEmbedding(model_name=MODEL, specific_model_path=str(self.directory / "files"),
                                        local_files_only=True, threads=2, providers=["CPUExecutionProvider"])
            self._tokenizer = Tokenizer.from_file(str(self.directory / "files" / "tokenizer.json"))
            self._tokenizer.no_truncation()
            self._tokenizer.no_padding()

    def embed(self, texts, kind="document"):
        self._load()
        groups, chunks = [], []
        for value in texts:
            ids = self._tokenizer.encode(value, add_special_tokens=False).ids
            parts = [self._tokenizer.decode(ids[i:i + 96], skip_special_tokens=True) for i in range(0, len(ids), 96)] or [value]
            groups.append(len(parts)); chunks.extend(parts)
        method = self._model.query_embed if kind == "query" else self._model.passage_embed
        vectors = list(method(chunks, batch_size=32))
        output, start = [], 0
        for count in groups:
            output.append([sum(float(v[j]) for v in vectors[start:start + count]) / count for j in range(self.dimensions)])
            start += count
        return output
