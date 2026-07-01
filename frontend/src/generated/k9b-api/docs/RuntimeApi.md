# RuntimeApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getRuntimeStatus**](RuntimeApi.md#getruntimestatus) | **GET** /api/runtime-status | Get runtime status |



## getRuntimeStatus

> object getRuntimeStatus()

Get runtime status

Get current runtime status and diagnostics information.

### Example

```ts
import {
  Configuration,
  RuntimeApi,
} from '';
import type { GetRuntimeStatusRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new RuntimeApi();

  try {
    const data = await api.getRuntimeStatus();
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

**object**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Runtime status |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

