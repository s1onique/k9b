# AlertmanagerApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getAlertmanagerSourceDebugPacket**](AlertmanagerApi.md#getalertmanagersourcedebugpacket) | **GET** /api/runs/{run_id}/alertmanager-sources/debug-packet | Get AlertManager source debug packet |
| [**getAlertmanagerSourcePromotionReview**](AlertmanagerApi.md#getalertmanagersourcepromotionreview) | **GET** /api/runs/{run_id}/alertmanager-sources/promotion-review | Get AlertManager source promotion review |
| [**getAlertmanagerSourcesReviewPacket**](AlertmanagerApi.md#getalertmanagersourcesreviewpacket) | **GET** /api/runs/{run_id}/alertmanager-sources/review-packet | Get AlertManager sources review packet |
| [**performAlertmanagerSourceAction**](AlertmanagerApi.md#performalertmanagersourceactionoperation) | **POST** /api/runs/{run_id}/alertmanager-sources/action | Perform AlertManager source action |
| [**probeAlertmanagerSource**](AlertmanagerApi.md#probealertmanagersourceoperation) | **POST** /api/runs/{run_id}/alertmanager-sources/debug-packet/probe | Probe AlertManager source now |



## getAlertmanagerSourceDebugPacket

> object getAlertmanagerSourceDebugPacket(runId, sourceId)

Get AlertManager source debug packet

Get a debug packet for a specific AlertManager source with probe and discovery details. The sourceId is supplied via the required &#x60;&#x60;sourceId&#x60;&#x60; query parameter so the URL path does not need to be slashed-encoded.

### Example

```ts
import {
  Configuration,
  AlertmanagerApi,
} from '';
import type { GetAlertmanagerSourceDebugPacketRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AlertmanagerApi();

  const body = {
    // string
    runId: runId_example,
    // string
    sourceId: sourceId_example,
  } satisfies GetAlertmanagerSourceDebugPacketRequest;

  try {
    const data = await api.getAlertmanagerSourceDebugPacket(body);
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
| **runId** | `string` |  | [Defaults to `undefined`] |
| **sourceId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Debug packet generated |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getAlertmanagerSourcePromotionReview

> object getAlertmanagerSourcePromotionReview(runId, sourceId)

Get AlertManager source promotion review

Get a pre-promotion review assessing risk before promoting a source to manual. The sourceId is supplied via the required &#x60;&#x60;sourceId&#x60;&#x60; query parameter so the URL path does not need to be slashed-encoded.

### Example

```ts
import {
  Configuration,
  AlertmanagerApi,
} from '';
import type { GetAlertmanagerSourcePromotionReviewRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AlertmanagerApi();

  const body = {
    // string
    runId: runId_example,
    // string
    sourceId: sourceId_example,
  } satisfies GetAlertmanagerSourcePromotionReviewRequest;

  try {
    const data = await api.getAlertmanagerSourcePromotionReview(body);
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
| **runId** | `string` |  | [Defaults to `undefined`] |
| **sourceId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Promotion review generated |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getAlertmanagerSourcesReviewPacket

> object getAlertmanagerSourcesReviewPacket(runId)

Get AlertManager sources review packet

Get the review packet explaining why multiple AlertManager sources were discovered.

### Example

```ts
import {
  Configuration,
  AlertmanagerApi,
} from '';
import type { GetAlertmanagerSourcesReviewPacketRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AlertmanagerApi();

  const body = {
    // string
    runId: runId_example,
  } satisfies GetAlertmanagerSourcesReviewPacketRequest;

  try {
    const data = await api.getAlertmanagerSourcesReviewPacket(body);
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
| **runId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Review packet generated |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## performAlertmanagerSourceAction

> object performAlertmanagerSourceAction(runId, performAlertmanagerSourceActionRequest)

Perform AlertManager source action

Perform an action (promote/disable) on an AlertManager source. The sourceId is transported in the JSON request body so opaque identifiers that contain \&#39;/\&#39; do not need URL encoding.

### Example

```ts
import {
  Configuration,
  AlertmanagerApi,
} from '';
import type { PerformAlertmanagerSourceActionOperationRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AlertmanagerApi();

  const body = {
    // string
    runId: runId_example,
    // PerformAlertmanagerSourceActionRequest
    performAlertmanagerSourceActionRequest: ...,
  } satisfies PerformAlertmanagerSourceActionOperationRequest;

  try {
    const data = await api.performAlertmanagerSourceAction(body);
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
| **runId** | `string` |  | [Defaults to `undefined`] |
| **performAlertmanagerSourceActionRequest** | [PerformAlertmanagerSourceActionRequest](PerformAlertmanagerSourceActionRequest.md) |  | |

### Return type

**object**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Action performed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## probeAlertmanagerSource

> object probeAlertmanagerSource(runId, probeAlertmanagerSourceRequest)

Probe AlertManager source now

Run a live probe on the AlertManager source and return the updated debug packet. The sourceId is supplied in the JSON request body.

### Example

```ts
import {
  Configuration,
  AlertmanagerApi,
} from '';
import type { ProbeAlertmanagerSourceOperationRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AlertmanagerApi();

  const body = {
    // string
    runId: runId_example,
    // ProbeAlertmanagerSourceRequest
    probeAlertmanagerSourceRequest: ...,
  } satisfies ProbeAlertmanagerSourceOperationRequest;

  try {
    const data = await api.probeAlertmanagerSource(body);
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
| **runId** | `string` |  | [Defaults to `undefined`] |
| **probeAlertmanagerSourceRequest** | [ProbeAlertmanagerSourceRequest](ProbeAlertmanagerSourceRequest.md) |  | |

### Return type

**object**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Probe completed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
