#import <Foundation/Foundation.h>
#import <CoreServices/CoreServices.h>
#import <dispatch/dispatch.h>

static NSURL *checker;

static void checkNotes(void) {
    @autoreleasepool {
        NSTask *task = [[NSTask alloc] init];
        task.executableURL = checker;
        task.arguments = @[@"--check"];
        NSError *error = nil;
        if (![task launchAndReturnError:&error]) {
            NSLog(@"Не удалось запустить save_notes: %@", error);
            return;
        }
        [task waitUntilExit];
        if (task.terminationStatus != 0)
            NSLog(@"save_notes --check завершился с кодом %d", task.terminationStatus);
    }
}

static void filesChanged(ConstFSEventStreamRef stream, void *context, size_t count,
                         void *paths, const FSEventStreamEventFlags flags[],
                         const FSEventStreamEventId ids[]) {
    for (size_t i = 0; i < count; ++i) {
        if (flags[i] & kFSEventStreamEventFlagRootChanged)
            exit(1);  // launchd will subscribe to the new root.
        if (flags[i] & kFSEventStreamEventFlagHistoryDone)
            continue;
        if (flags[i] & (kFSEventStreamEventFlagItemIsFile |
                        kFSEventStreamEventFlagMustScanSubDirs)) {
            checkNotes();
            return;
        }
    }
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 4) return 2;
        NSString *root = [NSString stringWithUTF8String:argv[1]];
        checker = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[2]]];
        int seconds = [[NSString stringWithUTF8String:argv[3]] intValue];
        if (seconds <= 0) return 2;

        FSEventStreamRef stream = FSEventStreamCreate(
            NULL, filesChanged, NULL, (__bridge CFArrayRef)@[root],
            kFSEventStreamEventIdSinceNow, 0.25,
            kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagWatchRoot);
        if (!stream) return 1;
        FSEventStreamSetDispatchQueue(stream, dispatch_get_main_queue());
        if (!FSEventStreamStart(stream)) return 1;

        dispatch_source_t timer = dispatch_source_create(
            DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
        int64_t interval = (int64_t)seconds * NSEC_PER_SEC;
        dispatch_source_set_timer(timer, dispatch_walltime(NULL, interval), interval,
                                  NSEC_PER_SEC);
        dispatch_source_set_event_handler(timer, ^{ checkNotes(); });
        dispatch_resume(timer);
        // Keep the timer alive for the full lifetime of the event loop under ARC.
        __attribute__((objc_precise_lifetime)) dispatch_source_t liveTimer = timer;
        (void)liveTimer;
        checkNotes();
        dispatch_main();
    }
}
