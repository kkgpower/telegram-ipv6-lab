package org.telegram.messenger;

/** Push is intentionally disabled for the standalone IPv6 lab application. */
final class Ipv6LabPushListenerServiceProvider implements PushListenerController.IPushListenerServiceProvider {
    static final Ipv6LabPushListenerServiceProvider INSTANCE = new Ipv6LabPushListenerServiceProvider();

    private Ipv6LabPushListenerServiceProvider() {
    }

    @Override
    public boolean hasServices() {
        return false;
    }

    @Override
    public String getLogTitle() {
        return "IPv6 lab (push disabled)";
    }

    @Override
    public void onRequestPushToken() {
        // The lab has no Firebase project and must never request a Firebase token.
    }

    @Override
    public int getPushType() {
        return PushListenerController.PUSH_TYPE_FIREBASE;
    }
}
