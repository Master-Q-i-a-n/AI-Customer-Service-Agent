package com.wly.workorder.auth;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class RegisterRequest {
  @NotBlank
  private String username;

  @NotBlank
  private String password;

  @NotBlank
  private String displayName;

  private String avatarUrl;

  @NotNull
  private AuthRole role;
}
