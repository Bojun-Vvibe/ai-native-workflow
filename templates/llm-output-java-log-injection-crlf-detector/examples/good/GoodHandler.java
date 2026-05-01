package com.example.good;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Good samples for java-log-injection-crlf detector.
// None of these should produce a finding.

public class GoodHandler {
    private static final Logger log = LoggerFactory.getLogger(GoodHandler.class);
    private static final Logger LOGGER = LoggerFactory.getLogger("audit");

    public void onStartup() {
        // Safe: fully literal.
        log.info("starting up");
    }

    public void onShutdown() {
        // Safe: literal at WARN level.
        LOGGER.warn("shutdown requested");
    }

    public void onLogin(String username) {
        // Safe: parameterised logging with placeholder, no concat.
        // (Out of scope for this detector — sink-side handling.)
        String safe = username.replaceAll("[\\r\\n\\t]", "_");
        log.info("user logged in: {}", safe);
    }

    public void onQuery(String q) {
        // Safe: parameterised with multiple placeholders.
        String safeQ = q.replaceAll("[\\r\\n\\t]", "_");
        LOGGER.debug("query={} duration={}ms", safeQ, 12);
    }

    public void onCount(int count, String status) {
        // Safe: literal template + parameterised values.
        log.info("processed {} items, status={}", count, status);
    }

    public void onMessage(String message) {
        // Safe: bare allow-listed name (message), not a tainted suffix.
        log.info(message);
    }

    public void onAudited(String userInput) {
        // Safe: explicit suppression marker after audit.
        log.warn("audited: " + userInput); // llm-allow:log-injection
    }

    public void onMath(int a, int b) {
        // Safe: ++ / += do not register as concat.
        int n = a;
        n++;
        n += b;
        log.info("computed n={}", n);
    }

    public void onComment() {
        // Safe: a // comment that mentions log.info("x=" + y) is stripped.
        log.info("done");
    }
}
