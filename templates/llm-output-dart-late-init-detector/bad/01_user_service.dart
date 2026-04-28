class UserService {
  late String currentUserId;
  late final ApiClient client;

  void boot(String id, ApiClient c) {
    currentUserId = id;
    client = c;
  }
}

class ApiClient {}
