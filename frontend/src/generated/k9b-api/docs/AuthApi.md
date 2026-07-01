# AuthApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getAuthMe**](AuthApi.md#getauthme) | **GET** /api/auth/me | Get current user info |
| [**getAuthStatus**](AuthApi.md#getauthstatus) | **GET** /api/auth/status | Get authentication status |
| [**postAuthLogin**](AuthApi.md#postauthloginoperation) | **POST** /api/auth/login | Login |
| [**postAuthLogout**](AuthApi.md#postauthlogout) | **POST** /api/auth/logout | Logout |



## getAuthMe

> GetAuthMe200Response getAuthMe()

Get current user info

Get information about the currently authenticated user.

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { GetAuthMeRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AuthApi();

  try {
    const data = await api.getAuthMe();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**GetAuthMe200Response**](GetAuthMe200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Current user info |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getAuthStatus

> GetAuthStatus200Response getAuthStatus()

Get authentication status

Check if the current session is authenticated and get session info.

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { GetAuthStatusRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AuthApi();

  try {
    const data = await api.getAuthStatus();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**GetAuthStatus200Response**](GetAuthStatus200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Authentication status |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## postAuthLogin

> PostAuthLogin200Response postAuthLogin(postAuthLoginRequest)

Login

Authenticate with username and password to create a session.

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { PostAuthLoginOperationRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AuthApi();

  const body = {
    // PostAuthLoginRequest
    postAuthLoginRequest: ...,
  } satisfies PostAuthLoginOperationRequest;

  try {
    const data = await api.postAuthLogin(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **postAuthLoginRequest** | [PostAuthLoginRequest](PostAuthLoginRequest.md) |  | |

### Return type

[**PostAuthLogin200Response**](PostAuthLogin200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Login successful |  -  |
| **401** | Invalid credentials |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## postAuthLogout

> PostAuthLogin200Response postAuthLogout()

Logout

Terminate the current session.

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { PostAuthLogoutRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AuthApi();

  try {
    const data = await api.postAuthLogout();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**PostAuthLogin200Response**](PostAuthLogin200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Logout successful |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

