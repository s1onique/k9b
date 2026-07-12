# OpenapiApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getApiDocs**](OpenapiApi.md#getapidocs) | **GET** /api/docs | API documentation browser |
| [**getOpenapiSchema**](OpenapiApi.md#getopenapischema) | **GET** /api/openapi.json | Get OpenAPI schema |



## getApiDocs

> string getApiDocs()

API documentation browser

Returns an API reference HTML page that loads /api/openapi.json.

### Example

```ts
import {
  Configuration,
  OpenapiApi,
} from '';
import type { GetApiDocsRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new OpenapiApi();

  try {
    const data = await api.getApiDocs();
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

**string**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | API reference HTML page |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getOpenapiSchema

> object getOpenapiSchema()

Get OpenAPI schema

Returns the OpenAPI 3.1 schema as JSON for API introspection.

### Example

```ts
import {
  Configuration,
  OpenapiApi,
} from '';
import type { GetOpenapiSchemaRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new OpenapiApi();

  try {
    const data = await api.getOpenapiSchema();
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
| **200** | OpenAPI 3.1 schema |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
