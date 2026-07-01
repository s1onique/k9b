# IncidentsApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**approveNextCheck**](IncidentsApi.md#approvenextcheck) | **POST** /api/next-check-approval | Approve next-check |
| [**captureIncidentSnapshot**](IncidentsApi.md#captureincidentsnapshot) | **POST** /api/incidents/snapshot | Capture incident snapshot |
| [**createIncidentReviewPacket**](IncidentsApi.md#createincidentreviewpacket) | **POST** /api/incidents/review-packet | Generate incident review packet |
| [**executeNextCheck**](IncidentsApi.md#executenextcheck) | **POST** /api/next-check-execution | Execute next-check |
| [**getClusterDetail**](IncidentsApi.md#getclusterdetail) | **GET** /api/cluster-detail | Get cluster detail |
| [**getFleet**](IncidentsApi.md#getfleet) | **GET** /api/fleet | Get fleet overview |
| [**getIncidentDetail**](IncidentsApi.md#getincidentdetail) | **GET** /api/incidents/{incident_id} | Get incident detail |
| [**getIncidentDiagnosisReviewHandoff**](IncidentsApi.md#getincidentdiagnosisreviewhandoff) | **GET** /api/incidents/{incident_id}/automatic-diagnosis-review/handoff | Get automatic diagnosis review handoff |
| [**getProposals**](IncidentsApi.md#getproposals) | **GET** /api/proposals | Get proposals |
| [**getRunDetail**](IncidentsApi.md#getrundetail) | **GET** /api/run | Get selected run detail |
| [**listIncidents**](IncidentsApi.md#listincidents) | **GET** /api/incidents | List incidents |
| [**listNotifications**](IncidentsApi.md#listnotifications) | **GET** /api/notifications | List notifications |
| [**listRuns**](IncidentsApi.md#listruns) | **GET** /api/runs | List runs |
| [**performAlertmanagerSourceAction**](IncidentsApi.md#performalertmanagersourceaction) | **POST** /api/runs/{run_id}/alertmanager-sources/{source_id}/action | Perform AlertManager source action |
| [**promoteDeterministicNextCheck**](IncidentsApi.md#promotedeterministicnextcheck) | **POST** /api/deterministic-next-check/promote | Promote deterministic next-check |
| [**recordAlertmanagerRelevanceFeedback**](IncidentsApi.md#recordalertmanagerrelevancefeedback) | **POST** /api/alertmanager-relevance-feedback | Record AlertManager relevance feedback |
| [**recordNextCheckUsefulness**](IncidentsApi.md#recordnextcheckusefulness) | **POST** /api/next-check-execution-usefulness | Record next-check usefulness feedback |
| [**runBatchNextCheckExecution**](IncidentsApi.md#runbatchnextcheckexecution) | **POST** /api/run-batch-next-check-execution | Batch execute next-checks |
| [**runIncidentAutomaticDiagnosisLoop**](IncidentsApi.md#runincidentautomaticdiagnosisloop) | **POST** /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass | Run automatic diagnosis loop one-pass |
| [**runIncidentDiagnosisLoop**](IncidentsApi.md#runincidentdiagnosisloop) | **POST** /api/incidents/{incident_id}/diagnosis-loop/one-pass | Run one-pass diagnosis loop |
| [**runIncidentOnePassDiagnosis**](IncidentsApi.md#runincidentonepassdiagnosis) | **POST** /api/incidents/{incident_id}/one-pass-diagnosis | Run one-pass diagnosis service |



## approveNextCheck

> object approveNextCheck()

Approve next-check

Approve a next-check for execution.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { ApproveNextCheckRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.approveNextCheck();
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
| **200** | Approval recorded |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## captureIncidentSnapshot

> CaptureIncidentSnapshot200Response captureIncidentSnapshot()

Capture incident snapshot

Capture a cluster snapshot for the current state.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { CaptureIncidentSnapshotRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.captureIncidentSnapshot();
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

[**CaptureIncidentSnapshot200Response**](CaptureIncidentSnapshot200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Snapshot captured |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createIncidentReviewPacket

> CreateIncidentReviewPacket200Response createIncidentReviewPacket()

Generate incident review packet

Generate a diagnostic review packet for an incident.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { CreateIncidentReviewPacketRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.createIncidentReviewPacket();
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

[**CreateIncidentReviewPacket200Response**](CreateIncidentReviewPacket200Response.md)

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


## executeNextCheck

> object executeNextCheck()

Execute next-check

Execute a next-check with manual input.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { ExecuteNextCheckRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.executeNextCheck();
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
| **200** | Execution completed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getClusterDetail

> object getClusterDetail(clusterLabel)

Get cluster detail

Get detailed information for a specific cluster.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { GetClusterDetailRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string (optional)
    clusterLabel: clusterLabel_example,
  } satisfies GetClusterDetailRequest;

  try {
    const data = await api.getClusterDetail(body);
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
| **clusterLabel** | `string` |  | [Optional] [Defaults to `undefined`] |

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
| **200** | Cluster detail |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getFleet

> object getFleet()

Get fleet overview

Get overview of all clusters in the fleet.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { GetFleetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.getFleet();
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
| **200** | Fleet overview |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getIncidentDetail

> object getIncidentDetail(incidentId)

Get incident detail

Get details for a specific incident by ID.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { GetIncidentDetailRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string
    incidentId: incidentId_example,
  } satisfies GetIncidentDetailRequest;

  try {
    const data = await api.getIncidentDetail(body);
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
| **200** | Incident details |  -  |
| **404** | Incident not found |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getIncidentDiagnosisReviewHandoff

> object getIncidentDiagnosisReviewHandoff(incidentId)

Get automatic diagnosis review handoff

Get the handoff artifact for automatic diagnosis review.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { GetIncidentDiagnosisReviewHandoffRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

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


## getProposals

> object getProposals()

Get proposals

Get diagnostic proposals for the current run.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { GetProposalsRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.getProposals();
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
| **200** | Proposals list |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getRunDetail

> object getRunDetail(runId)

Get selected run detail

Get details for the selected run.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { GetRunDetailRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string (optional)
    runId: runId_example,
  } satisfies GetRunDetailRequest;

  try {
    const data = await api.getRunDetail(body);
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
| **runId** | `string` |  | [Optional] [Defaults to `undefined`] |

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
| **200** | Run details |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## listIncidents

> ListIncidents200Response listIncidents(status, limit, page)

List incidents

List all incidents with optional status filter.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { ListIncidentsRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string (optional)
    status: status_example,
    // string (optional)
    limit: limit_example,
    // string (optional)
    page: page_example,
  } satisfies ListIncidentsRequest;

  try {
    const data = await api.listIncidents(body);
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
| **status** | `string` |  | [Optional] [Defaults to `undefined`] |
| **limit** | `string` |  | [Optional] [Defaults to `undefined`] |
| **page** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

[**ListIncidents200Response**](ListIncidents200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | List of incidents |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## listNotifications

> ListNotifications200Response listNotifications(kind, clusterLabel, search, limit, page)

List notifications

List notifications with optional filters.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { ListNotificationsRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string (optional)
    kind: kind_example,
    // string (optional)
    clusterLabel: clusterLabel_example,
    // string (optional)
    search: search_example,
    // string (optional)
    limit: limit_example,
    // string (optional)
    page: page_example,
  } satisfies ListNotificationsRequest;

  try {
    const data = await api.listNotifications(body);
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
| **kind** | `string` |  | [Optional] [Defaults to `undefined`] |
| **clusterLabel** | `string` |  | [Optional] [Defaults to `undefined`] |
| **search** | `string` |  | [Optional] [Defaults to `undefined`] |
| **limit** | `string` |  | [Optional] [Defaults to `undefined`] |
| **page** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

[**ListNotifications200Response**](ListNotifications200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Notifications list |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## listRuns

> ListRuns200Response listRuns(limit, page, clusterLabel)

List runs

List all diagnostic runs with pagination.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { ListRunsRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string (optional)
    limit: limit_example,
    // string (optional)
    page: page_example,
    // string (optional)
    clusterLabel: clusterLabel_example,
  } satisfies ListRunsRequest;

  try {
    const data = await api.listRuns(body);
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
| **limit** | `string` |  | [Optional] [Defaults to `undefined`] |
| **page** | `string` |  | [Optional] [Defaults to `undefined`] |
| **clusterLabel** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

[**ListRuns200Response**](ListRuns200Response.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | List of runs |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## performAlertmanagerSourceAction

> object performAlertmanagerSourceAction(runId, sourceId)

Perform AlertManager source action

Perform an action (promote/disable) on an AlertManager source.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { PerformAlertmanagerSourceActionRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  const body = {
    // string
    runId: runId_example,
    // string
    sourceId: sourceId_example,
  } satisfies PerformAlertmanagerSourceActionRequest;

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
| **200** | Action performed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## promoteDeterministicNextCheck

> object promoteDeterministicNextCheck()

Promote deterministic next-check

Promote a deterministic next-check candidate.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { PromoteDeterministicNextCheckRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.promoteDeterministicNextCheck();
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
| **200** | Promotion successful |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## recordAlertmanagerRelevanceFeedback

> object recordAlertmanagerRelevanceFeedback()

Record AlertManager relevance feedback

Record operator feedback on AlertManager source relevance.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { RecordAlertmanagerRelevanceFeedbackRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.recordAlertmanagerRelevanceFeedback();
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
| **200** | Feedback recorded |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## recordNextCheckUsefulness

> object recordNextCheckUsefulness()

Record next-check usefulness feedback

Record operator feedback on next-check usefulness.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { RecordNextCheckUsefulnessRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.recordNextCheckUsefulness();
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
| **200** | Feedback recorded |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## runBatchNextCheckExecution

> object runBatchNextCheckExecution()

Batch execute next-checks

Execute multiple next-checks in batch.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { RunBatchNextCheckExecutionRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

  try {
    const data = await api.runBatchNextCheckExecution();
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
| **200** | Batch execution completed |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## runIncidentAutomaticDiagnosisLoop

> object runIncidentAutomaticDiagnosisLoop(incidentId)

Run automatic diagnosis loop one-pass

Execute automatic diagnosis loop one-pass using the real collector.

### Example

```ts
import {
  Configuration,
  IncidentsApi,
} from '';
import type { RunIncidentAutomaticDiagnosisLoopRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

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
  IncidentsApi,
} from '';
import type { RunIncidentDiagnosisLoopRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

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
  IncidentsApi,
} from '';
import type { RunIncidentOnePassDiagnosisRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new IncidentsApi();

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

