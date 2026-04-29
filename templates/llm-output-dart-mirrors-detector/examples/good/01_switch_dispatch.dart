// Static dispatch via switch -- safe.
class Service {
  void ping() {}
  void shutdown() {}
}

void run(String userMethod, Service s) {
  switch (userMethod) {
    case 'ping':
      s.ping();
      break;
    case 'shutdown':
      s.shutdown();
      break;
    default:
      throw ArgumentError('unknown: $userMethod');
  }
}
