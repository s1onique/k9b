# DiagnosisApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getIncidentDiagnosisReviewHandoff**](DiagnosisApi.md#getincidentdiagnosisreviewhandoff) | **GET** /api/incidents/{incident_id}/automatic-diagnosis-review/handoff | Get automatic diagnosis review handoff |
| [**runIncidentAutomaticDiagnosisLoop**](DiagnosisApi.md#runincidentautomaticdiagnosisloop) | **POST** /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass | Run automatic diagnosis loop one-pass |
| [**runIncidentDiagnosisLoop**](DiagnosisApi.md#runincidentdiagnosisloop) | **POST** /api/incidents/{incident_id}/diagnosis-loop/one-pass | Run one-pass diagnosis loop |
| [**runIncidentOnePassDiagnosis**](DiagnosisApi.md#runincidentonepassdiagnosis) | **POST** /api/incidents/{incident_id}/one-pass-diagnosis | Run one-pass diagnosis service |



## getIncidentDiagnosisReviewHandoff

> object getIncidentDiagnosisReviewHandoff(incidentId)

Get automatic diagnosis review handoff

Get the handoff artifact for automatic diagnosis review.

### Example

```ts
import {
  Configuration,
  DiagnosisApi,
} from '';
import type { GetIncidentDiagnosisReviewHandoffRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DiagnosisApi();

  const body = {
    // string
    incidentId: incidentId_example,
  } satisfies GetIncidentDiagnosisReviewHandoffRequest;

  try {
    const data = await api.getIncidentDiagnosisReviewHandoff(body);
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
| **incidentId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Diagnosis review handoff |  -  |
| **404** | Incident or handoff not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## runIncidentAutomaticDiagnosisLoop

> object runIncidentAutomaticDiagnosisLoop(incidentId)

Run automatic diagnosis loop one-pass

Execute automatic diagnosis loop one-pass using the real collector.

### Example

```ts
import {
  Configuration,
  DiagnosisApi,
} from '';
import type { RunIncidentAutomaticDiagnosisLoopRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DiagnosisApi();

  const body = {
    // string
    incidentId: incidentId_example,
  } satisfies RunIncidentAutomaticDiagnosisLoopRequest;

  try {
    const data = await api.runIncidentAutomaticDiagnosisLoop(body);
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
| **incidentId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Automatic diagnosis completed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## runIncidentDiagnosisLoop

> object runIncidentDiagnosisLoop(incidentId)

Run one-pass diagnosis loop

Execute a single pass of the diagnosis loop for an incident.

### Example

```ts
import {
  Configuration,
  DiagnosisApi,
} from '';
import type { RunIncidentDiagnosisLoopRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DiagnosisApi();

  const body = {
    // string
    incidentId: incidentId_example,
  } satisfies RunIncidentDiagnosisLoopRequest;

  try {
    const data = await api.runIncidentDiagnosisLoop(body);
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
| **incidentId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Diagnosis loop completed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## runIncidentOnePassDiagnosis

> object runIncidentOnePassDiagnosis(incidentId)

Run one-pass diagnosis service

Execute one-pass diagnosis using the diagnosis service.

### Example

```ts
import {
  Configuration,
  DiagnosisApi,
} from '';
import type { RunIncidentOnePassDiagnosisRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DiagnosisApi();

  const body = {
    // string
    incidentId: incidentId_example,
  } satisfies RunIncidentOnePassDiagnosisRequest;

  try {
    const data = await api.runIncidentOnePassDiagnosis(body);
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
| **incidentId** | `string` |  | [Defaults to `undefined`] |

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
| **200** | Diagnosis completed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

