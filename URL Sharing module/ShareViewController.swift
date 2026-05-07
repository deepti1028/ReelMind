import UIKit
import UniformTypeIdentifiers
import os

// MARK: - Logger
// Apple's unified logging via os.Logger.
//
// Why os.Logger over print():
//   - print() output is unreliable from share extensions (separate process,
//     stdout sometimes never reaches Xcode's console).
//   - os.Logger writes to the system log; visible in BOTH Xcode's debug
//     console AND Console.app on Mac (filter by subsystem).
//   - Levels (debug/info/notice/warning/error) integrate with Console.app's
//     filter UI, so you can hide noise.
//
// Why `privacy: .public`:
//   By default, dynamic strings interpolated into Logger messages are marked
//   PRIVATE — they appear as "<private>" in Console.app outside Xcode. For
//   development logs we want everything visible, so each call site marks the
//   message as `.public`.
//
// To view in Console.app on Mac:
//   1. Open Console.app, select your iPhone (or simulator) in the sidebar
//   2. Type in the search bar: subsystem:com.deepti.ReelMind.ShareExtension
//   3. Click "Start Streaming"
private enum Log {
    private static let logger = Logger(
        subsystem: "com.deepti.ReelMind.ShareExtension",
        category: "share"
    )

    static func debug(_ message: String)   { logger.debug("🔍 [DEBUG]   \(message, privacy: .public)") }
    static func info(_ message: String)    { logger.info("ℹ️  [INFO]    \(message, privacy: .public)") }
    static func warn(_ message: String)    { logger.warning("⚠️  [WARN]    \(message, privacy: .public)") }
    static func error(_ message: String)   { logger.error("❌ [ERROR]   \(message, privacy: .public)") }
    static func success(_ message: String) { logger.notice("✅ [SUCCESS] \(message, privacy: .public)") }
    static func event(_ message: String)   { logger.notice("🎬 [EVENT]   \(message, privacy: .public)") }
    static func net(_ message: String)     { logger.notice("🌐 [NET]     \(message, privacy: .public)") }
}

class ShareViewController: UIViewController {

    private enum K {
        static let appGroupID = "group.com.deepti.ReelMind"
        static let backendBaseURL = "https://reelmind-api.onrender.com"
        static let pendingURLsKey = "pendingReelURLs"
        static let authTokenKey = "supabaseAuthToken"

        // Bottom sheet sizing
        static let sheetHeightRatio: CGFloat = 0.55    // 55% of screen (40% + 15% per spec)

        // Animation timeline
        // Exit is handled entirely by iOS's dismissal animation (no manual slide-down).
        // We just call completeRequest() and let iOS take both the chrome and our
        // sheet off-screen together — eliminates the white-reveal gap that happens
        // when our sheet slides down ahead of the chrome.
        static let slideUpDuration: TimeInterval = 0.35
        static let progressFillDuration: TimeInterval = 0.8
        static let savingToSavedAt: TimeInterval = 0.8
        static let dismissAt: TimeInterval = 1.9    // 0.8s saving + 0.2s fade-out + 0.5s checkmark pop + 0.4s settle
    }

    // MARK: - Colors

    private static let sheetColor = UIColor(red: 26/255, green: 26/255, blue: 26/255, alpha: 1)
    private static let dragHandleColor = UIColor(white: 68/255, alpha: 1)
    private static let secondaryTextColor = UIColor(white: 153/255, alpha: 1)

    // MARK: - UI

    private let bottomSheet: UIView = {
        let v = UIView()
        v.backgroundColor = ShareViewController.sheetColor
        v.layer.cornerRadius = 20
        v.layer.maskedCorners = [.layerMinXMinYCorner, .layerMaxXMinYCorner]
        v.layer.shadowColor = UIColor.black.cgColor
        v.layer.shadowOpacity = 0.5
        v.layer.shadowRadius = 20
        v.layer.shadowOffset = CGSize(width: 0, height: -4)
        v.translatesAutoresizingMaskIntoConstraints = false
        return v
    }()

    private let dragHandle: UIView = {
        let v = UIView()
        v.backgroundColor = ShareViewController.dragHandleColor
        v.layer.cornerRadius = 2
        v.translatesAutoresizingMaskIntoConstraints = false
        return v
    }()

    // Saving state — alpha defaults to 1 so it's visible from frame 0
    private let savingContainer: UIView = {
        let v = UIView()
        v.translatesAutoresizingMaskIntoConstraints = false
        v.alpha = 1
        return v
    }()
    // Native iOS spinner — replaces the custom CAShapeLayer progress ring.
    // Why: the custom ring (white outline circle) was visually too similar to
    // the checkmark wrapper (white filled circle) that appears right after,
    // creating a "loader appears twice" perception. The native spinner is
    // unambiguously a "loading" indicator and looks nothing like the checkmark.
    private let savingSpinner: UIActivityIndicatorView = {
        let s = UIActivityIndicatorView(style: .large)
        s.color = .white
        s.hidesWhenStopped = false
        s.translatesAutoresizingMaskIntoConstraints = false
        return s
    }()
    private let savingLabel = UILabel()
    private let savingInfoLabel = UILabel()

    // Saved state — alpha forced to 0 at construction so the two states never overlap visually.
    private let savedContainer: UIView = {
        let v = UIView()
        v.translatesAutoresizingMaskIntoConstraints = false
        v.alpha = 0
        return v
    }()
    private let checkmarkCircle = UIView()
    private let checkmarkLabel = UILabel()
    private let savedTitleLabel = UILabel()
    private let savedInfoLabel = UILabel()

    // MARK: - Idempotency flags
    //
    // Share-extension lifecycle is finicky — iOS sometimes fires viewWillAppear
    // and/or viewDidAppear more than once during a single presentation (e.g.
    // when the extension's view is re-laid out, when the parent host briefly
    // hides it, etc.). Without guards, we'd kick off the slide-up and progress
    // animations again, which the user perceives as a "double loader".
    private var hasStartedSlideUp = false
    private var hasStartedTimeline = false

    // MARK: - Lifecycle

    override func viewDidLoad() {
        super.viewDidLoad()
        Log.event("viewDidLoad — share extension launched")
        view.backgroundColor = .clear
        setupUI()
        // Position sheet off-screen BEFORE first frame renders to avoid a flash.
        bottomSheet.transform = CGAffineTransform(translationX: 0, y: 1500)
        Log.debug("UI hierarchy built; sheet pre-positioned off-screen (sheet ratio=\(K.sheetHeightRatio))")
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        clearAncestorBackgrounds()

        guard !hasStartedSlideUp else {
            Log.debug("viewWillAppear fired again — slide-up already started, skipping")
            return
        }
        hasStartedSlideUp = true

        // Two strategies for syncing the slide-up with iOS's chrome animation:
        //
        // 1. transitionCoordinator (preferred when available) — gives us a hook
        //    into the same animation block iOS uses for its chrome. We animate
        //    inside `animate(alongsideTransition:)` and both move in lockstep.
        //
        // 2. Fire spring animation immediately in viewWillAppear (fallback) —
        //    share extensions on most iOS versions DON'T expose a coordinator
        //    here, so we kick off the animation manually. Because viewWillAppear
        //    fires *while* iOS is animating its chrome in (not after, like
        //    viewDidAppear), our 0.35s spring runs during the same window.
        //    Result: chrome and sheet arrive in place at roughly the same time.
        //
        // Either way the slide-up never waits for viewDidAppear.
        if let coordinator = transitionCoordinator {
            Log.debug("Animating slide-up alongside iOS presentation (transitionCoordinator hooked)")
            coordinator.animate(alongsideTransition: { _ in
                self.bottomSheet.transform = .identity
            }, completion: nil)
        } else {
            Log.debug("No transitionCoordinator — running spring slide-up in viewWillAppear (parallel to iOS chrome)")
            UIView.animate(
                withDuration: K.slideUpDuration,
                delay: 0,
                usingSpringWithDamping: 0.75,
                initialSpringVelocity: 0.4,
                options: .curveEaseOut,
                animations: { self.bottomSheet.transform = .identity },
                completion: nil
            )
        }
    }

    private func clearAncestorBackgrounds() {
        var ancestor: UIView? = view
        var depth = 0
        while let v = ancestor {
            v.backgroundColor = .clear
            ancestor = v.superview
            depth += 1
        }
        Log.debug("Cleared backgrounds on \(depth) ancestor view(s) for host app visibility")
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)

        guard !hasStartedTimeline else {
            Log.debug("viewDidAppear fired again — timeline already running, skipping")
            return
        }
        hasStartedTimeline = true

        Log.event("viewDidAppear — starting progress + URL extraction (sheet already mid-slide-up from viewWillAppear)")

        // Slide-up was already kicked off in viewWillAppear (either via the
        // transitionCoordinator or via the fallback spring). By the time we get
        // here, the sheet is partway up or has finished animating.
        startProgressAndStateTimeline()
        extractAndHandleURL()
    }

    // MARK: - UI Setup

    private func setupUI() {
        view.addSubview(bottomSheet)
        bottomSheet.addSubview(dragHandle)
        setupSavingState()
        setupSavedState()

        NSLayoutConstraint.activate([
            bottomSheet.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            bottomSheet.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            bottomSheet.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            bottomSheet.heightAnchor.constraint(equalTo: view.heightAnchor, multiplier: K.sheetHeightRatio),

            dragHandle.topAnchor.constraint(equalTo: bottomSheet.topAnchor, constant: 10),
            dragHandle.centerXAnchor.constraint(equalTo: bottomSheet.centerXAnchor),
            dragHandle.widthAnchor.constraint(equalToConstant: 36),
            dragHandle.heightAnchor.constraint(equalToConstant: 4),

            savingContainer.centerXAnchor.constraint(equalTo: bottomSheet.centerXAnchor),
            savingContainer.centerYAnchor.constraint(equalTo: bottomSheet.centerYAnchor),
            savedContainer.centerXAnchor.constraint(equalTo: bottomSheet.centerXAnchor),
            savedContainer.centerYAnchor.constraint(equalTo: bottomSheet.centerYAnchor),
        ])
        Log.debug("Layout constraints activated")
    }

    private func setupSavingState() {
        bottomSheet.addSubview(savingContainer)
        savingContainer.addSubview(savingSpinner)

        savingLabel.text = "Saving..."
        savingLabel.font = .systemFont(ofSize: 14, weight: .semibold)
        savingLabel.textColor = .white
        savingLabel.translatesAutoresizingMaskIntoConstraints = false
        savingContainer.addSubview(savingLabel)

        savingInfoLabel.font = .systemFont(ofSize: 12, weight: .regular)
        savingInfoLabel.textColor = ShareViewController.secondaryTextColor
        savingInfoLabel.translatesAutoresizingMaskIntoConstraints = false
        savingContainer.addSubview(savingInfoLabel)

        NSLayoutConstraint.activate([
            savingSpinner.topAnchor.constraint(equalTo: savingContainer.topAnchor),
            savingSpinner.centerXAnchor.constraint(equalTo: savingContainer.centerXAnchor),

            savingLabel.topAnchor.constraint(equalTo: savingSpinner.bottomAnchor, constant: 16),
            savingLabel.centerXAnchor.constraint(equalTo: savingContainer.centerXAnchor),

            savingInfoLabel.topAnchor.constraint(equalTo: savingLabel.bottomAnchor, constant: 4),
            savingInfoLabel.centerXAnchor.constraint(equalTo: savingContainer.centerXAnchor),
            savingInfoLabel.bottomAnchor.constraint(equalTo: savingContainer.bottomAnchor),
        ])
    }

    private func setupSavedState() {
        bottomSheet.addSubview(savedContainer)

        checkmarkCircle.backgroundColor = .white
        checkmarkCircle.layer.cornerRadius = 36
        checkmarkCircle.layer.shadowColor = UIColor.black.cgColor
        checkmarkCircle.layer.shadowOpacity = 0.25
        checkmarkCircle.layer.shadowRadius = 14
        checkmarkCircle.layer.shadowOffset = CGSize(width: 0, height: 12)
        checkmarkCircle.translatesAutoresizingMaskIntoConstraints = false
        savedContainer.addSubview(checkmarkCircle)

        checkmarkLabel.text = "✓"
        checkmarkLabel.font = .systemFont(ofSize: 36, weight: .bold)
        checkmarkLabel.textColor = .black
        checkmarkLabel.textAlignment = .center
        checkmarkLabel.translatesAutoresizingMaskIntoConstraints = false
        checkmarkCircle.addSubview(checkmarkLabel)

        savedTitleLabel.text = "Saved!"
        savedTitleLabel.font = .systemFont(ofSize: 17, weight: .bold)
        savedTitleLabel.textColor = .white
        savedTitleLabel.translatesAutoresizingMaskIntoConstraints = false
        savedContainer.addSubview(savedTitleLabel)

        savedInfoLabel.text = "Reel added to Reelmind"
        savedInfoLabel.font = .systemFont(ofSize: 12, weight: .regular)
        savedInfoLabel.textColor = ShareViewController.secondaryTextColor
        savedInfoLabel.translatesAutoresizingMaskIntoConstraints = false
        savedContainer.addSubview(savedInfoLabel)

        NSLayoutConstraint.activate([
            checkmarkCircle.topAnchor.constraint(equalTo: savedContainer.topAnchor),
            checkmarkCircle.centerXAnchor.constraint(equalTo: savedContainer.centerXAnchor),
            checkmarkCircle.widthAnchor.constraint(equalToConstant: 72),
            checkmarkCircle.heightAnchor.constraint(equalToConstant: 72),

            checkmarkLabel.centerXAnchor.constraint(equalTo: checkmarkCircle.centerXAnchor),
            checkmarkLabel.centerYAnchor.constraint(equalTo: checkmarkCircle.centerYAnchor, constant: -2),

            savedTitleLabel.topAnchor.constraint(equalTo: checkmarkCircle.bottomAnchor, constant: 12),
            savedTitleLabel.centerXAnchor.constraint(equalTo: savedContainer.centerXAnchor),

            savedInfoLabel.topAnchor.constraint(equalTo: savedTitleLabel.bottomAnchor, constant: 4),
            savedInfoLabel.centerXAnchor.constraint(equalTo: savedContainer.centerXAnchor),
            savedInfoLabel.bottomAnchor.constraint(equalTo: savedContainer.bottomAnchor),
        ])
    }

    // MARK: - URL Extraction

    private func extractAndHandleURL() {
        Log.event("Starting URL extraction from share context")

        guard let items = extensionContext?.inputItems as? [NSExtensionItem], !items.isEmpty else {
            Log.error("No input items found — dismissing without animation")
            finish()
            return
        }
        Log.debug("Received \(items.count) input item(s)")

        let group = DispatchGroup()
        var extracted: URL?

        outer: for (i, item) in items.enumerated() {
            let attachments = item.attachments ?? []
            Log.debug("Item \(i) has \(attachments.count) attachment(s)")

            for (j, provider) in attachments.enumerated() {
                if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    Log.info("Attachment \(j) conforms to public.url — loading")
                    group.enter()
                    provider.loadItem(forTypeIdentifier: UTType.url.identifier) { data, err in
                        if let err = err {
                            Log.error("loadItem(public.url) failed: \(err.localizedDescription)")
                        }
                        if let url = data as? URL {
                            extracted = url
                            Log.success("Extracted URL: \(url.absoluteString)")
                        } else {
                            Log.warn("loadItem returned non-URL data: \(String(describing: data))")
                        }
                        group.leave()
                    }
                    break outer
                }

                if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                    Log.info("Attachment \(j) conforms to public.plain-text — loading as fallback")
                    group.enter()
                    provider.loadItem(forTypeIdentifier: UTType.plainText.identifier) { data, err in
                        if let err = err {
                            Log.error("loadItem(plainText) failed: \(err.localizedDescription)")
                        }
                        if let text = data as? String, let url = URL(string: text) {
                            extracted = url
                            Log.success("Extracted URL from text: \(url.absoluteString)")
                        } else {
                            Log.warn("Could not parse URL from text: \(String(describing: data))")
                        }
                        group.leave()
                    }
                    break outer
                }
            }
        }

        group.notify(queue: .main) { [weak self] in
            guard let self else { return }
            if let url = extracted {
                Log.success("URL extraction complete — performing save (animation already running)")
                self.handleURL(url)
            } else {
                Log.error("No URL could be extracted from any attachment — animation continues but no save performed")
            }
        }
    }

    // MARK: - URL Handling

    private func handleURL(_ url: URL) {
        Log.event("handleURL invoked for: \(url.absoluteString)")
        writeURLToAppGroup(url)
        let token = readAuthToken()
        postURLToBackend(url: url, authToken: token)
    }

    private func writeURLToAppGroup(_ url: URL) {
        guard let defaults = UserDefaults(suiteName: K.appGroupID) else {
            Log.error("Could not access App Group UserDefaults — check entitlement (\(K.appGroupID))")
            return
        }
        var queue = defaults.stringArray(forKey: K.pendingURLsKey) ?? []
        let str = url.absoluteString
        let alreadyQueued = queue.contains(str)
        if !alreadyQueued {
            queue.append(str)
            defaults.set(queue, forKey: K.pendingURLsKey)
            Log.success("Wrote URL to App Group queue (size=\(queue.count))")
        } else {
            Log.warn("URL already in App Group queue — dedup skipped write")
        }
    }

    private func readAuthToken() -> String {
        let token = UserDefaults(suiteName: K.appGroupID)?.string(forKey: K.authTokenKey) ?? ""
        if token.isEmpty {
            Log.warn("No auth token found in App Group — backend will reject 401")
        } else {
            Log.debug("Auth token loaded (length=\(token.count))")
        }
        return token
    }

    // MARK: - Backend POST

    private func postURLToBackend(url: URL, authToken: String) {
        guard let apiURL = URL(string: "\(K.backendBaseURL)/api/v1/reels") else {
            Log.error("Invalid backend URL constant — \(K.backendBaseURL)")
            return
        }

        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 10
        let bodyDict: [String: Any] = ["url": url.absoluteString]
        request.httpBody = try? JSONSerialization.data(withJSONObject: bodyDict)

        Log.net("➡️  POST \(apiURL.absoluteString)")
        Log.net("    Headers: Content-Type=application/json, Authorization=Bearer \(authToken.isEmpty ? "<empty>" : "<\(authToken.count)-char-token>")")
        Log.net("    Body: \(bodyDict)")

        let startTime = Date()
        URLSession.shared.dataTask(with: request) { data, response, error in
            let elapsed = String(format: "%.0f", Date().timeIntervalSince(startTime) * 1000)

            if let error = error {
                Log.error("⬅️  POST failed (\(elapsed)ms): \(error.localizedDescription)")
                return
            }

            if let http = response as? HTTPURLResponse {
                let status = http.statusCode
                let prefix: String
                switch status {
                case 200...299: prefix = "✅"
                case 400...499: prefix = "⚠️ "
                case 500...599: prefix = "❌"
                default: prefix = "ℹ️ "
                }
                Log.net("\(prefix) ⬅️  POST \(status) (\(elapsed)ms)")

                if let data = data, !data.isEmpty,
                   let bodyStr = String(data: data, encoding: .utf8) {
                    Log.net("    Response body: \(bodyStr.prefix(500))")
                }
            } else {
                Log.warn("⬅️  POST returned non-HTTP response (\(elapsed)ms)")
            }
        }.resume()
    }

    // MARK: - Animation Sequence

    private func startProgressAndStateTimeline() {
        Log.event("Starting native spinner + state transition timeline")

        // Native iOS spinner spins on its own — no Core Animation choreography
        // needed. It just animates indefinitely until we hide it.
        savingSpinner.startAnimating()

        DispatchQueue.main.asyncAfter(deadline: .now() + K.savingToSavedAt) { [weak self] in
            Log.event("Transitioning to saved state")
            self?.transitionToSavedState()
        }

        // No manual slide-down. iOS's own dismissal animation will carry the
        // chrome AND our sheet off-screen together in a single smooth motion.
        DispatchQueue.main.asyncAfter(deadline: .now() + K.dismissAt) { [weak self] in
            Log.event("Saved state shown — handing off to iOS for dismissal")
            self?.finish()
        }
    }

    private func transitionToSavedState() {
        // Pre-stage the saved state OFFSCREEN-EQUIVALENT — checkmark is at
        // scale ~0 and labels are alpha 0, so even though savedContainer.alpha
        // is 1, the contents are invisible. This keeps us from competing with
        // the saving content during the cross-fade.
        savedContainer.alpha = 1
        savedTitleLabel.alpha = 0
        savedInfoLabel.alpha = 0
        checkmarkCircle.transform = CGAffineTransform(scaleX: 0.001, y: 0.001)

        // Fade the saving content out completely BEFORE the checkmark pops.
        // Sequential transition keeps the spinner and checkmark from ever
        // being on screen at the same time.
        UIView.animate(withDuration: 0.2, animations: {
            self.savingContainer.alpha = 0
        }, completion: { _ in
            self.savingSpinner.stopAnimating()
            // Now that saving is fully gone, pop the checkmark in.
            UIView.animate(
                withDuration: 0.5,
                delay: 0,
                usingSpringWithDamping: 0.55,
                initialSpringVelocity: 0.8,
                options: .curveEaseOut,
                animations: {
                    self.checkmarkCircle.transform = .identity
                }
            )

            UIView.animate(withDuration: 0.4, delay: 0.1, options: .curveEaseOut) {
                self.savedTitleLabel.alpha = 1
            }
            UIView.animate(withDuration: 0.4, delay: 0.2, options: .curveEaseOut) {
                self.savedInfoLabel.alpha = 1
            }
        })
    }

    // MARK: - Dismiss

    private func finish() {
        Log.success("Extension finishing — host app will be reactivated")
        extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
    }
}
