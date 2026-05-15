package com.wly.workorder.auth;

public interface AuthService {
  LoginResponse register(RegisterRequest request);

  LoginResponse login(LoginRequest request);

  UserProfile me();

  DemoAccountResponse getDemoAccount(String username);

  UserProfile updateProfile(UpdateProfileRequest request);

  UserProfile updatePassword(UpdatePasswordRequest request);

  void deleteAccount();

  AuthSession requireSession();
}
