const fs=require('fs'),vm=require('vm'),assert=require('assert');
const dir='/tmp/harness-skill-eval-20261103/independent';
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.handlers={};this.hidden=false;this.textContent=''}
 append(...nodes){this.children.push(...nodes)}
 setAttribute(key,value){this.attributes[key]=value}
 addEventListener(event,handler){this.handlers[event]=handler}
 replaceChildren(...nodes){this.children=nodes}
}
let results=[];
for(const name of ['corrected']){
 const quiz=JSON.parse(fs.readFileSync(`${dir}/${name}-quiz.json`,'utf8'));
 const root=new Element('div'), data=new Element('script');data.textContent=JSON.stringify(quiz);
 const document={getElementById:id=>id==='quiz-data'?data:root,createElement:tag=>new Element(tag)};
 vm.runInNewContext(fs.readFileSync(`${dir}/${name}-quiz.js`,'utf8'),{document});
 assert.equal(root.children.length,5);
 for(let i=0;i<5;i++){
  const field=root.children[i];assert.equal(field.tagName,'fieldset');
  const buttons=field.children.filter(x=>x.tagName==='button');const feedback=field.children.at(-1);
  assert.equal(buttons.length,4);assert.equal(feedback.hidden,true);assert.equal(feedback.children.length,0);assert(buttons.every(b=>b.attributes['aria-pressed']==='false'));
  for(let j=0;j<4;j++){
   buttons[j].handlers.click();assert.equal(feedback.hidden,false);
   assert.equal(buttons.filter(b=>b.attributes['aria-pressed']==='true').length,1);
   assert.equal(buttons[j].attributes['aria-pressed'],'true');
   const isRight=quiz[i].options[j].id===quiz[i].correct_option_id;
   assert.equal(feedback.children[0].textContent,isRight?'Верно.':'Не совсем.');
   assert.equal(feedback.children[1].textContent,quiz[i].options[j].explanation);
   assert.equal(feedback.children.length,isRight?2:3);
   if(!isRight)assert(feedback.children[2].textContent.includes(quiz[i].options.find(o=>o.id===quiz[i].correct_option_id).text));
  }
 }
 results.push({document:name,initial_hidden:true,initial_unselected:true,questions:5,click_paths_tested:20,reselection:true,verdicts_and_feedback:true});
}
fs.writeFileSync(`${dir}/corrected-dom-results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
