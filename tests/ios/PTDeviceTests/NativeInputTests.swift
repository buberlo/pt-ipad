import XCTest

final class NativeInputTests: XCTestCase {
    private let game = XCUIApplication(bundleIdentifier: "com.konradkern.pt.native")

    override func setUpWithError() throws {
        continueAfterFailure = false
        guard game.state == .notRunning else {
            throw XCTSkip("Preserve the existing P.T. session; run when the app is closed.")
        }
    }

    private func waitSeconds(_ seconds: TimeInterval) {
        let delay = expectation(description: "Allow real-time game progression")
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { delay.fulfill() }
        wait(for: [delay], timeout: seconds + 5)
    }

    private func capture(_ name: String) {
        XCTAssertEqual(game.state, .runningForeground)
        let image = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        image.name = name
        image.lifetime = .keepAlways
        add(image)
    }

    private func point(_ x: CGFloat, _ y: CGFloat) -> XCUICoordinate {
        game.coordinate(withNormalizedOffset: CGVector(dx: x, dy: y))
    }

    func testTouchAndResume() throws {
        let session = try XCTUnwrap(ProcessInfo.processInfo.environment["PT_TEST_SESSION"],
                                   "Run through device_ui_test.py with an isolated device session")
        XCTAssertTrue(session.hasPrefix("/private/") && session.contains("/Documents/PTDiagnostics/"))
        // This exercises real touchscreen events. The script only records state.
        // The host runner requires real step-15 position/yaw changes and matching
        // pause/background/resume logs in addition to a passing XCTest result.
        game.launchArguments = ["--no-save", "--no-mods", "--start-floor", "f010",
            "--settings", session + "/session.ini", "--log", session + "/pt.log", "--input",
            stride(from: 0, through: 18000, by: 15).map { "\($0) log" }.joined(separator: "; ")]
        game.launchEnvironment = ["PT_LOG_TICKS": "1", "PT_SYSTEM_LANGUAGE": "en-US"]
        game.launch()
        defer { game.terminate() }
        XCTAssertTrue(game.wait(for: .runningForeground, timeout: 30))
        waitSeconds(30)
        capture("01-starting-room")
        point(0.60, 0.48).press(forDuration: 0.1, thenDragTo: point(0.75, 0.48))
        waitSeconds(1)
        capture("02-look-right")
        point(0.75, 0.48).press(forDuration: 0.1, thenDragTo: point(0.60, 0.48))
        point(0.17, 0.79).press(forDuration: 0.1, thenDragTo: point(0.17, 0.64),
                              withVelocity: 120, thenHoldForDuration: 3)
        waitSeconds(1)
        capture("03-move-forward")
        point(0.90, 0.72).tap()
        point(0.81, 0.87).press(forDuration: 1)
        capture("04-interact-and-zoom")
        point(0.92, 0.10).tap()
        waitSeconds(1)
        capture("05-pause")
        point(0.90, 0.06).tap() // Separate menu Continue control.
        waitSeconds(1)
        XCUIDevice.shared.press(.home)
        XCTAssertTrue(game.wait(for: .runningBackground, timeout: 10))
        waitSeconds(3)
        game.activate()
        XCTAssertTrue(game.wait(for: .runningForeground, timeout: 10))
        waitSeconds(3)
        capture("06-resumed")
    }
}
