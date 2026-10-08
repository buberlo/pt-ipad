/* SPDX-License-Identifier: MIT */
/* Copyright (C) 2026 buberlo */
#import <UIKit/UIKit.h>
#import <sys/utsname.h>
#include "../gpu-probe/gpu_probe.h"

@interface ProbeAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation ProbeAppDelegate
@end

@interface ProbeDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) UITextView *status;
@property(nonatomic) BOOL started;
@property(atomic) BOOL interrupted;
@end
@implementation ProbeDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    UIViewController *controller = [UIViewController new];
    controller.view.backgroundColor = UIColor.systemBackgroundColor;
    self.status = [[UITextView alloc] initWithFrame:controller.view.bounds];
    self.status.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    self.status.editable = NO;
    self.status.font = [UIFont monospacedSystemFontOfSize:16 weight:UIFontWeightRegular];
    self.status.textContainerInset = UIEdgeInsetsMake(70, 24, 24, 24);
    self.status.text = @"AnyPS5 · GPU-Prüfung\n\nWarte auf aktiven Vordergrund …";
    [controller.view addSubview:self.status];
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(applicationBecameActive:)
        name:UIApplicationDidBecomeActiveNotification object:nil];
}
- (void)sceneDidBecomeActive:(UIScene *)scene {
    [self startProbeForScene:scene];
}
- (void)applicationBecameActive:(NSNotification *)notification {
    (void)notification;
    [self startProbeForScene:self.window.windowScene];
}
- (void)startProbeForScene:(UIScene *)scene {
    if (self.started) return;
    if (!scene || scene.activationState != UISceneActivationStateForegroundActive) return;
    UIApplication *application = UIApplication.sharedApplication;
    // UIKit may deliver sceneDidBecomeActive before the application transition
    // completes. Its did-become-active notification retries this exact gate.
    if (application.applicationState != UIApplicationStateActive) return;
    self.started = YES;
    application.idleTimerDisabled = YES;
    self.status.text = @"AnyPS5 · GPU-Prüfung\n\nGerät und Shader werden geprüft …\n\nDieser Test prüft MoltenVK direkt. Wine/FEX und ein Spiel werden separat getestet.";
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString *reportPath = [documents stringByAppendingPathComponent:@"gpu-probe.jsonl"];
    NSString *shaderDirectory = NSBundle.mainBundle.resourcePath;
    NSData *manifestData = [NSData dataWithContentsOfFile:[shaderDirectory stringByAppendingPathComponent:@"manifest.json"]];
    NSDictionary *manifest = manifestData ? [NSJSONSerialization JSONObjectWithData:manifestData options:0 error:nil] : nil;
    struct utsname system; uname(&system);
    NSDictionary *metadata = @{@"schema":@1, @"stage":@"native_gpu", @"test":@"device_context",
        @"model":@(system.machine), @"os":NSProcessInfo.processInfo.operatingSystemVersionString,
        @"physical_memory_bytes":@(NSProcessInfo.processInfo.physicalMemory),
        @"application_state":@(application.applicationState),
        @"scene_activation_state":@(scene.activationState),
        @"thermal_state":@(NSProcessInfo.processInfo.thermalState),
        @"low_power_mode":@(NSProcessInfo.processInfo.lowPowerModeEnabled),
        @"build_manifest":manifest ?: @{},
        @"timestamp":@([[NSDate date] timeIntervalSince1970])};
    NSData *metadataJSON = [NSJSONSerialization dataWithJSONObject:metadata options:0 error:nil];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        FILE *report = fopen(reportPath.fileSystemRepresentation, "w");
        int code = 2;
        if (report) {
            fwrite(metadataJSON.bytes, 1, metadataJSON.length, report); fputc('\n', report); fflush(report);
            code = aps5_gpu_probe_run(shaderDirectory.fileSystemRepresentation, report);
            fclose(report);
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            application.idleTimerDisabled = NO;
            BOOL foregroundPass = !self.interrupted && application.applicationState == UIApplicationStateActive &&
                scene.activationState == UISceneActivationStateForegroundActive;
            NSDictionary *completion = @{@"schema":@1, @"stage":@"native_gpu", @"test":@"foreground_completion",
                @"interrupted":@(self.interrupted), @"application_state":@(application.applicationState),
                @"scene_activation_state":@(scene.activationState),
                @"thermal_state":@(NSProcessInfo.processInfo.thermalState),
                @"pass":@(foregroundPass), @"gpu_exit_code":@(code),
                @"native_offscreen_accepted":@(foregroundPass && code == 0),
                @"visible_gameplay_verified":@NO, @"timestamp":@([[NSDate date] timeIntervalSince1970])};
            NSData *completionJSON = [NSJSONSerialization dataWithJSONObject:completion options:0 error:nil];
            FILE *append = fopen(reportPath.fileSystemRepresentation, "a");
            if (append) {
                fwrite(completionJSON.bytes, 1, completionJSON.length, append); fputc('\n', append); fclose(append);
            }
            NSString *log = [NSString stringWithContentsOfFile:reportPath encoding:NSUTF8StringEncoding error:nil] ?: @"Bericht konnte nicht geschrieben werden.";
            self.status.text = [NSString stringWithFormat:@"AnyPS5 · GPU-Prüfung\n\n%@\n\n%@\n\nBericht: Dateien → AnyPS5 GPU Probe → gpu-probe.jsonl",
                !foregroundPass ? @"Test wurde unterbrochen. App für eine gültige Messung neu starten." :
                (code == 0 ? @"GPU-Berechnung und Rücklesen bestanden." : @"Prüfung fehlgeschlagen. Details stehen im Bericht."), log];
        });
    });
}
- (void)sceneWillResignActive:(UIScene *)scene {
    (void)scene;
    if (self.started) self.interrupted = YES;
}
- (void)sceneDidDisconnect:(UIScene *)scene {
    (void)scene;
    if (self.started) self.interrupted = YES;
    [NSNotificationCenter.defaultCenter removeObserver:self];
}
@end

int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeAppDelegate.class)); }
}
