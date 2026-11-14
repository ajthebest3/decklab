package com.marketdeck.app;

import java.util.LinkedHashMap;

/** Per-resource health keyed by origin then path. Pure Java, no Android deps. */
final class ResourceHealth {
    private static final int MAX_ORIGINS = 4;
    private static final int MAX_PATHS_PER_ORIGIN = 128;
    private static final int MAX_ERROR_CHARS = 300;

    static final class Snapshot {
        final long lastAttemptMs;
        final long lastSuccessMs;
        final String error;

        Snapshot(long lastAttemptMs, long lastSuccessMs, String error) {
            this.lastAttemptMs = lastAttemptMs;
            this.lastSuccessMs = lastSuccessMs;
            this.error = error;
        }

        boolean fresh(long now, long maxAgeMs) {
            return lastSuccessMs > 0L
                    && lastSuccessMs <= now
                    && now - lastSuccessMs <= maxAgeMs
                    && (error == null || error.isEmpty());
        }
    }

    private final LinkedHashMap<String, LinkedHashMap<String, Snapshot>> byOrigin =
            new LinkedHashMap<String, LinkedHashMap<String, Snapshot>>();

    synchronized void attempted(String origin, String path, long now) {
        Snapshot prior = get(origin, path);
        record(origin, path, new Snapshot(now, prior.lastSuccessMs, prior.error));
    }

    /** Clears only this exact origin+path failure; other keys are untouched. */
    synchronized void succeeded(String origin, String path, long now) {
        record(origin, path, new Snapshot(now, now, null));
    }

    synchronized void failed(String origin, String path, long now, String error) {
        Snapshot prior = get(origin, path);
        record(origin, path, new Snapshot(now, prior.lastSuccessMs, bound(error)));
    }

    /** Unknown (zero, no error) when never seen or evicted. */
    synchronized Snapshot get(String origin, String path) {
        if (origin == null || path == null) {
            return new Snapshot(0L, 0L, null);
        }
        LinkedHashMap<String, Snapshot> paths = byOrigin.get(origin);
        Snapshot snapshot = paths == null ? null : paths.get(path);
        return snapshot == null ? new Snapshot(0L, 0L, null) : snapshot;
    }

    private void record(String origin, String path, Snapshot snapshot) {
        if (origin == null || path == null) {
            return;
        }
        LinkedHashMap<String, Snapshot> paths = byOrigin.get(origin);
        if (paths == null) {
            if (byOrigin.size() >= MAX_ORIGINS) {
                byOrigin.remove(byOrigin.keySet().iterator().next());
            }
            paths = new LinkedHashMap<String, Snapshot>();
            byOrigin.put(origin, paths);
        }
        paths.put(path, snapshot);
        while (paths.size() > MAX_PATHS_PER_ORIGIN) {
            paths.remove(paths.keySet().iterator().next());
        }
    }

    private static String bound(String error) {
        String value = (error == null || error.isEmpty()) ? "failed" : error;
        if (value.length() <= MAX_ERROR_CHARS) {
            return value;
        }
        int end = Character.isHighSurrogate(value.charAt(MAX_ERROR_CHARS - 1))
                ? MAX_ERROR_CHARS - 1 : MAX_ERROR_CHARS;
        return value.substring(0, end);
    }
}
