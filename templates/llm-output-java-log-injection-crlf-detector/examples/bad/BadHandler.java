package com.example.bad;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.text.MessageFormat;

// Bad samples for java-log-injection-crlf detector.
// Each line listed below should yield exactly one finding.

public class BadHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger(BadHandler.class);
    private static final Logger log = LoggerFactory.getLogger("audit");

    public void onLogin(String username) {
        // 1. java-log-injection-concat: classic + concat
        log.info("user logged in: " + username);
    }

    public void onQuery(String q) {
        // 2. java-log-injection-concat: WARN level
        LOGGER.warn("query=" + q);
    }

    public void onError(String input) {
        // 3. java-log-injection-format: String.format pre-rendered
        LOGGER.error(String.format("failed for %s", input));
    }

    public void onPrefix(String input) {
        // 4. java-log-injection-concat: tainted prefix
        log.info(input + " requested resource");
    }

    public void onParam(String reqParam) {
        // 5. java-log-injection-bare-tainted: bare *Param identifier
        log.debug(reqParam);
    }

    public void onHeader(String authHeader) {
        // 6. java-log-injection-bare-tainted: bare *Header identifier
        LOGGER.warn(authHeader);
    }

    public void onMessageFormat(String input) {
        // 7. java-log-injection-format: MessageFormat.format pre-rendered
        log.error(MessageFormat.format("input was: {0}", input));
    }

    public void onFormatted(String input) {
        // 8. java-log-injection-format: .formatted() (Java 15+)
        log.info("payload=%s".formatted(input));
    }

    public void onTrace(String userInput) {
        // 9. java-log-injection-bare-tainted: known tainted name
        log.trace(userInput);
    }
}
