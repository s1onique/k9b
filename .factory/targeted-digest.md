# Targeted digest

Generated at: 2026-07-12T00:28:28Z
Repo: /Users/chistyakov/Projects/SPbNIX/k9b
Mode: staged

## Manifest
files_changed=75
added_files=8
modified_files=67
renamed_files=0
deleted_files=0

M	docs/api/openapi/k9b-openapi-baseline.json
M	docs/api/openapi/operation-ids-baseline.txt
M	frontend/src/__tests__/api.test.ts
M	frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts
M	frontend/src/api/alertmanager.ts
M	frontend/src/generated/k9b-api/.openapi-generator/FILES
A	frontend/src/generated/k9b-api/apis/AlertmanagerApi.ts
M	frontend/src/generated/k9b-api/apis/AuthApi.ts
M	frontend/src/generated/k9b-api/apis/DiagnosisApi.ts
M	frontend/src/generated/k9b-api/apis/HealthApi.ts
M	frontend/src/generated/k9b-api/apis/IncidentsApi.ts
M	frontend/src/generated/k9b-api/apis/OpenapiApi.ts
M	frontend/src/generated/k9b-api/apis/RuntimeApi.ts
M	frontend/src/generated/k9b-api/apis/index.ts
A	frontend/src/generated/k9b-api/docs/AlertmanagerApi.md
M	frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md
M	frontend/src/generated/k9b-api/docs/AuthApi.md
M	frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md
M	frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md
M	frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md
M	frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md
M	frontend/src/generated/k9b-api/docs/DiagnosisApi.md
M	frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md
M	frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md
M	frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md
M	frontend/src/generated/k9b-api/docs/GetHealth200Response.md
M	frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md
M	frontend/src/generated/k9b-api/docs/HealthApi.md
M	frontend/src/generated/k9b-api/docs/IncidentsApi.md
M	frontend/src/generated/k9b-api/docs/ListIncidents200Response.md
M	frontend/src/generated/k9b-api/docs/ListNotifications200Response.md
M	frontend/src/generated/k9b-api/docs/ListRuns200Response.md
M	frontend/src/generated/k9b-api/docs/OpenapiApi.md
M	frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md
M	frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md
M	frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md
A	frontend/src/generated/k9b-api/docs/ProbeAlertmanagerSourceRequest.md
M	frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md
M	frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md
M	frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md
M	frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md
M	frontend/src/generated/k9b-api/docs/RuntimeApi.md
M	frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts
M	frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts
M	frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts
M	frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts
M	frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts
M	frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts
M	frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts
M	frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts
M	frontend/src/generated/k9b-api/models/GetHealth200Response.ts
M	frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts
M	frontend/src/generated/k9b-api/models/ListIncidents200Response.ts
M	frontend/src/generated/k9b-api/models/ListNotifications200Response.ts
M	frontend/src/generated/k9b-api/models/ListRuns200Response.ts
M	frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts
M	frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts
M	frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts
A	frontend/src/generated/k9b-api/models/ProbeAlertmanagerSourceRequest.ts
M	frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts
M	frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts
M	frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts
M	frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts
M	frontend/src/generated/k9b-api/models/index.ts
M	frontend/src/generated/k9b-api/runtime.ts
A	scripts/_alertmanager_baseline_patch.py
M	scripts/generate_frontend_api_client.sh
A	scripts/normalize_generated_client.py
M	src/k8s_diag_agent/ui/api_contract.py
M	src/k8s_diag_agent/ui/api_contract_types.py
M	src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py
M	src/k8s_diag_agent/ui/api_request_schemas.py
M	src/k8s_diag_agent/ui/api_routes_nextcheck.py
A	tests/test_openapi_alertmanager_source_contract.py
A	tests/test_openapi_alertmanager_source_dispatch.py

## Changed files
docs/api/openapi/k9b-openapi-baseline.json  [tracked, staged present: yes, unstaged present: no]
docs/api/openapi/operation-ids-baseline.txt  [tracked, staged present: yes, unstaged present: no]
frontend/src/__tests__/api.test.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/api/alertmanager.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/.openapi-generator/FILES  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/AlertmanagerApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/AuthApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/DiagnosisApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/HealthApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/IncidentsApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/OpenapiApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/RuntimeApi.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/apis/index.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/AlertmanagerApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/AuthApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/DiagnosisApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/GetHealth200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/HealthApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/IncidentsApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/ListIncidents200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/ListNotifications200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/ListRuns200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/OpenapiApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/ProbeAlertmanagerSourceRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/docs/RuntimeApi.md  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/GetHealth200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/ListIncidents200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/ListNotifications200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/ListRuns200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/ProbeAlertmanagerSourceRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/models/index.ts  [tracked, staged present: yes, unstaged present: no]
frontend/src/generated/k9b-api/runtime.ts  [tracked, staged present: yes, unstaged present: no]
scripts/_alertmanager_baseline_patch.py  [tracked, staged present: yes, unstaged present: no]
scripts/generate_frontend_api_client.sh  [tracked, staged present: yes, unstaged present: no]
scripts/normalize_generated_client.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/api_contract.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/api_contract_types.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/api_request_schemas.py  [tracked, staged present: yes, unstaged present: no]
src/k8s_diag_agent/ui/api_routes_nextcheck.py  [tracked, staged present: yes, unstaged present: no]
tests/test_openapi_alertmanager_source_contract.py  [tracked, staged present: yes, unstaged present: no]
tests/test_openapi_alertmanager_source_dispatch.py  [tracked, staged present: yes, unstaged present: no]

## Diff stat
 docs/api/openapi/k9b-openapi-baseline.json         | 208 ++++++++++-
 docs/api/openapi/operation-ids-baseline.txt        |   6 +-
 frontend/src/__tests__/api.test.ts                 |   5 +-
 ...neratedPostWrappers.alertmanagerActions.test.ts |  24 +-
 frontend/src/api/alertmanager.ts                   | 164 +++++++--
 .../src/generated/k9b-api/.openapi-generator/FILES |   4 +
 .../src/generated/k9b-api/apis/AlertmanagerApi.ts  | 333 +++++++++++++++++
 frontend/src/generated/k9b-api/apis/AuthApi.ts     |   4 +-
 .../src/generated/k9b-api/apis/DiagnosisApi.ts     |   4 +-
 frontend/src/generated/k9b-api/apis/HealthApi.ts   |   4 +-
 .../src/generated/k9b-api/apis/IncidentsApi.ts     |  80 +---
 frontend/src/generated/k9b-api/apis/OpenapiApi.ts  |   4 +-
 frontend/src/generated/k9b-api/apis/RuntimeApi.ts  |   4 +-
 frontend/src/generated/k9b-api/apis/index.ts       |   1 +
 .../src/generated/k9b-api/docs/AlertmanagerApi.md  | 359 ++++++++++++++++++
 .../k9b-api/docs/ApproveNextCheckRequest.md        |   2 -
 frontend/src/generated/k9b-api/docs/AuthApi.md     |   1 -
 .../docs/CaptureIncidentSnapshot200Response.md     |   2 -
 .../k9b-api/docs/CaptureIncidentSnapshotRequest.md |   2 -
 .../docs/CreateIncidentReviewPacket200Response.md  |   2 -
 .../docs/CreateIncidentReviewPacketRequest.md      |   2 -
 .../src/generated/k9b-api/docs/DiagnosisApi.md     |   1 -
 .../k9b-api/docs/ExecuteNextCheckRequest.md        |   2 -
 .../generated/k9b-api/docs/GetAuthMe200Response.md |   2 -
 .../k9b-api/docs/GetAuthStatus200Response.md       |   2 -
 .../generated/k9b-api/docs/GetHealth200Response.md |   2 -
 .../k9b-api/docs/GetHealthDetails200Response.md    |   2 -
 frontend/src/generated/k9b-api/docs/HealthApi.md   |   1 -
 .../src/generated/k9b-api/docs/IncidentsApi.md     |  75 ----
 .../k9b-api/docs/ListIncidents200Response.md       |   2 -
 .../k9b-api/docs/ListNotifications200Response.md   |   2 -
 .../generated/k9b-api/docs/ListRuns200Response.md  |   2 -
 frontend/src/generated/k9b-api/docs/OpenapiApi.md  |   1 -
 .../docs/PerformAlertmanagerSourceActionRequest.md |   6 +-
 .../k9b-api/docs/PostAuthLogin200Response.md       |   2 -
 .../generated/k9b-api/docs/PostAuthLoginRequest.md |   2 -
 .../k9b-api/docs/ProbeAlertmanagerSourceRequest.md |  33 ++
 .../docs/PromoteDeterministicNextCheckRequest.md   |   2 -
 .../RecordAlertmanagerRelevanceFeedbackRequest.md  |   2 -
 .../docs/RecordNextCheckUsefulnessRequest.md       |   2 -
 .../docs/RunBatchNextCheckExecutionRequest.md      |   2 -
 frontend/src/generated/k9b-api/docs/RuntimeApi.md  |   1 -
 .../k9b-api/models/ApproveNextCheckRequest.ts      |   7 +-
 .../models/CaptureIncidentSnapshot200Response.ts   |  13 +-
 .../models/CaptureIncidentSnapshotRequest.ts       |   7 +-
 .../CreateIncidentReviewPacket200Response.ts       |  13 +-
 .../models/CreateIncidentReviewPacketRequest.ts    |   7 +-
 .../k9b-api/models/ExecuteNextCheckRequest.ts      |   7 +-
 .../k9b-api/models/GetAuthMe200Response.ts         |  11 +-
 .../k9b-api/models/GetAuthStatus200Response.ts     |  11 +-
 .../k9b-api/models/GetHealth200Response.ts         |  13 +-
 .../k9b-api/models/GetHealthDetails200Response.ts  |  13 +-
 .../k9b-api/models/ListIncidents200Response.ts     |  13 +-
 .../k9b-api/models/ListNotifications200Response.ts |  13 +-
 .../k9b-api/models/ListRuns200Response.ts          |  13 +-
 .../PerformAlertmanagerSourceActionRequest.ts      |  18 +-
 .../k9b-api/models/PostAuthLogin200Response.ts     |  11 +-
 .../k9b-api/models/PostAuthLoginRequest.ts         |  11 +-
 .../models/ProbeAlertmanagerSourceRequest.ts       |  65 ++++
 .../models/PromoteDeterministicNextCheckRequest.ts |   7 +-
 .../RecordAlertmanagerRelevanceFeedbackRequest.ts  |   7 +-
 .../models/RecordNextCheckUsefulnessRequest.ts     |   7 +-
 .../models/RunBatchNextCheckExecutionRequest.ts    |   7 +-
 frontend/src/generated/k9b-api/models/index.ts     |   1 +
 frontend/src/generated/k9b-api/runtime.ts          |   2 +-
 scripts/_alertmanager_baseline_patch.py            | 115 ++++++
 scripts/generate_frontend_api_client.sh            |  12 +-
 scripts/normalize_generated_client.py              | 102 ++++++
 src/k8s_diag_agent/ui/api_contract.py              |  16 +-
 src/k8s_diag_agent/ui/api_contract_types.py        |   5 +
 .../ui/api_dispatch_adapters_nextcheck.py          |  86 ++++-
 src/k8s_diag_agent/ui/api_request_schemas.py       |  18 +
 src/k8s_diag_agent/ui/api_routes_nextcheck.py      |  81 ++++-
 tests/test_openapi_alertmanager_source_contract.py | 405 +++++++++++++++++++++
 tests/test_openapi_alertmanager_source_dispatch.py | 273 ++++++++++++++
 75 files changed, 2334 insertions(+), 417 deletions(-)

## Diffs

=== docs/api/openapi/k9b-openapi-baseline.json ===
diff --git a/docs/api/openapi/k9b-openapi-baseline.json b/docs/api/openapi/k9b-openapi-baseline.json
index 69a314f..4d1d0ef 100644
--- a/docs/api/openapi/k9b-openapi-baseline.json
+++ b/docs/api/openapi/k9b-openapi-baseline.json
@@ -937,9 +937,9 @@
         ]
       }
     },
-    "/api/runs/{run_id}/alertmanager-sources/{source_id}/action": {
+    "/api/runs/{run_id}/alertmanager-sources/action": {
       "post": {
-        "description": "Perform an action (promote/disable) on an AlertManager source.",
+        "description": "Perform an action (promote/disable) on an AlertManager source. The sourceId is transported in the JSON request body so opaque identifiers that contain '/' do not need URL encoding.",
         "operationId": "perform_alertmanager_source_action",
         "parameters": [
           {
@@ -949,10 +949,77 @@
             "schema": {
               "type": "string"
             }
+          }
+        ],
+        "requestBody": {
+          "content": {
+            "application/json": {
+              "schema": {
+                "additionalProperties": false,
+                "description": "AlertManager source action request. sourceId is in body to support slashes in identifiers.",
+                "properties": {
+                  "action": {
+                    "description": "Action to perform (promote, disable)",
+                    "type": "string"
+                  },
+                  "clusterLabel": {
+                    "description": "Cluster label for override persistence",
+                    "type": "string"
+                  },
+                  "reason": {
+                    "description": "Optional reason for audit trail",
+                    "type": "string"
+                  },
+                  "sourceId": {
+                    "description": "AlertManager source identifier (may contain slashes)",
+                    "type": "string"
+                  }
+                },
+                "required": [
+                  "sourceId",
+                  "action",
+                  "clusterLabel"
+                ],
+                "type": "object"
+              }
+            }
           },
+          "required": true
+        },
+        "responses": {
+          "200": {
+            "content": {
+              "application/json": {
+                "schema": {
+                  "type": "object"
+                }
+              }
+            },
+            "description": "Action performed"
+          }
+        },
+        "summary": "Perform AlertManager source action",
+        "tags": [
+          "alertmanager"
+        ]
+      }
+    },
+    "/api/runs/{run_id}/alertmanager-sources/debug-packet": {
+      "get": {
+        "description": "Get a debug packet for a specific AlertManager source with probe and discovery details. The sourceId is supplied via the required ``sourceId`` query parameter so the URL path does not need to be slashed-encoded.",
+        "operationId": "get_alertmanager_source_debug_packet",
+        "parameters": [
           {
             "in": "path",
-            "name": "source_id",
+            "name": "run_id",
+            "required": true,
+            "schema": {
+              "type": "string"
+            }
+          },
+          {
+            "in": "query",
+            "name": "sourceId",
             "required": true,
             "schema": {
               "type": "string"
@@ -968,12 +1035,137 @@
                 }
               }
             },
-            "description": "Action performed"
+            "description": "Debug packet generated"
           }
         },
-        "summary": "Perform AlertManager source action",
+        "summary": "Get AlertManager source debug packet",
         "tags": [
-          "incidents"
+          "alertmanager"
+        ]
+      }
+    },
+    "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe": {
+      "post": {
+        "description": "Run a live probe on the AlertManager source and return the updated debug packet. The sourceId is supplied in the JSON request body.",
+        "operationId": "probe_alertmanager_source",
+        "parameters": [
+          {
+            "in": "path",
+            "name": "run_id",
+            "required": true,
+            "schema": {
+              "type": "string"
+            }
+          }
+        ],
+        "requestBody": {
+          "content": {
+            "application/json": {
+              "schema": {
+                "additionalProperties": false,
+                "description": "AlertManager source probe request. sourceId is in body to keep the POST path stable regardless of the source identifier content.",
+                "properties": {
+                  "sourceId": {
+                    "description": "AlertManager source identifier (may contain slashes)",
+                    "type": "string"
+                  }
+                },
+                "required": [
+                  "sourceId"
+                ],
+                "type": "object"
+              }
+            }
+          },
+          "required": true
+        },
+        "responses": {
+          "200": {
+            "content": {
+              "application/json": {
+                "schema": {
+                  "type": "object"
+                }
+              }
+            },
+            "description": "Probe completed"
+          }
+        },
+        "summary": "Probe AlertManager source now",
+        "tags": [
+          "alertmanager"
+        ]
+      }
+    },
+    "/api/runs/{run_id}/alertmanager-sources/promotion-review": {
+      "get": {
+        "description": "Get a pre-promotion review assessing risk before promoting a source to manual. The sourceId is supplied via the required ``sourceId`` query parameter so the URL path does not need to be slashed-encoded.",
+        "operationId": "get_alertmanager_source_promotion_review",
+        "parameters": [
+          {
+            "in": "path",
+            "name": "run_id",
+            "required": true,
+            "schema": {
+              "type": "string"
+            }
+          },
+          {
+            "in": "query",
+            "name": "sourceId",
+            "required": true,
+            "schema": {
+              "type": "string"
+            }
+          }
+        ],
+        "responses": {
+          "200": {
+            "content": {
+              "application/json": {
+                "schema": {
+                  "type": "object"
+                }
+              }
+            },
+            "description": "Promotion review generated"
+          }
+        },
+        "summary": "Get AlertManager source promotion review",
+        "tags": [
+          "alertmanager"
+        ]
+      }
+    },
+    "/api/runs/{run_id}/alertmanager-sources/review-packet": {
+      "get": {
+        "description": "Get the review packet explaining why multiple AlertManager sources were discovered.",
+        "operationId": "get_alertmanager_sources_review_packet",
+        "parameters": [
+          {
+            "in": "path",
+            "name": "run_id",
+            "required": true,
+            "schema": {
+              "type": "string"
+            }
+          }
+        ],
+        "responses": {
+          "200": {
+            "content": {
+              "application/json": {
+                "schema": {
+                  "type": "object"
+                }
+              }
+            },
+            "description": "Review packet generated"
+          }
+        },
+        "summary": "Get AlertManager sources review packet",
+        "tags": [
+          "alertmanager"
         ]
       }
     },
@@ -1025,6 +1217,10 @@
     {
       "description": "Runtime status and diagnostics endpoints.",
       "name": "runtime"
+    },
+    {
+      "description": "AlertManager source discovery, review, debug, and action endpoints. All AlertManager-source operations live under this single tag.",
+      "name": "alertmanager"
     }
   ]
 }

=== docs/api/openapi/operation-ids-baseline.txt ===
diff --git a/docs/api/openapi/operation-ids-baseline.txt b/docs/api/openapi/operation-ids-baseline.txt
index d703acc..fa9722e 100644
--- a/docs/api/openapi/operation-ids-baseline.txt
+++ b/docs/api/openapi/operation-ids-baseline.txt
@@ -31,5 +31,9 @@ GET /api/proposals get_proposals
 GET /api/run get_run_detail
 POST /api/run-batch-next-check-execution run_batch_next_check_execution
 GET /api/runs list_runs
-POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action perform_alertmanager_source_action
+POST /api/runs/{run_id}/alertmanager-sources/action perform_alertmanager_source_action
+GET /api/runs/{run_id}/alertmanager-sources/debug-packet get_alertmanager_source_debug_packet
+POST /api/runs/{run_id}/alertmanager-sources/debug-packet/probe probe_alertmanager_source
+GET /api/runs/{run_id}/alertmanager-sources/promotion-review get_alertmanager_source_promotion_review
+GET /api/runs/{run_id}/alertmanager-sources/review-packet get_alertmanager_sources_review_packet
 GET /api/runtime-status get_runtime_status

=== frontend/src/__tests__/api.test.ts ===
diff --git a/frontend/src/__tests__/api.test.ts b/frontend/src/__tests__/api.test.ts
index f53549f..6e7a9f2 100644
--- a/frontend/src/__tests__/api.test.ts
+++ b/frontend/src/__tests__/api.test.ts
@@ -563,12 +563,15 @@ describe("performAlertmanagerSourceAction", () => {
         }),
       })
     );
+    // The wrapper routes through the generated AlertmanagerApi client and
+    // ``normalizeGeneratedApiError`` falls back to a ``Request failed with
+    // status <code>`` message when the response body has no ``error`` field.
     await expect(
       performAlertmanagerSourceAction(
         { sourceId: "src-123", clusterLabel: "cluster-a", action: "promote" },
         "run-456"
       )
-    ).rejects.toThrow("HTTP 500:");
+    ).rejects.toThrow("Request failed with status 500");
   });

   test("sends sourceId with special characters in request body", async () => {

=== frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts ===
diff --git a/frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts b/frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts
index 7d80bb8..c791fce 100644
--- a/frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts
+++ b/frontend/src/__tests__/generatedPostWrappers.alertmanagerActions.test.ts
@@ -57,24 +57,30 @@ describe("performAlertmanagerSourceAction wrapper mapping", () => {
     expect(result.ok).toBe(true);

     // Regression guard: sourceId must be in POST body, not URL path
-    expect(fetch).toHaveBeenCalledWith(
-      "/api/runs/run-456/alertmanager-sources/action",
+    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
+    expect(url).toBe("/api/runs/run-456/alertmanager-sources/action");
+    expect(init).toEqual(
       expect.objectContaining({
         method: "POST",
+        credentials: "include",
         headers: expect.objectContaining({
           "Content-Type": "application/json",
         }),
-        body: JSON.stringify({
-          sourceId: "crd:monitoring.coreos.com/v1/Alertmanager/main",
-          action: "promote",
-          clusterLabel: "cluster-a",
-          reason: "Confirmed alert",
-        }),
       }),
     );

+    // Parse the body as JSON to verify its content (independent of property
+    // order, which depends on whether the wrapper routes through the
+    // generated client or uses direct fetch).
+    const body = JSON.parse((init as { body: string }).body);
+    expect(body).toEqual({
+      sourceId: "crd:monitoring.coreos.com/v1/Alertmanager/main",
+      action: "promote",
+      clusterLabel: "cluster-a",
+      reason: "Confirmed alert",
+    });
+
     // Verify sourceId is NOT in URL path (was the old buggy behavior)
-    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
     expect(url).not.toContain("crd:monitoring.coreos.com");
     expect(url).not.toContain("sourceId");
   });

=== frontend/src/api/alertmanager.ts ===
diff --git a/frontend/src/api/alertmanager.ts b/frontend/src/api/alertmanager.ts
index 3345539..9843b69 100644
--- a/frontend/src/api/alertmanager.ts
+++ b/frontend/src/api/alertmanager.ts
@@ -2,10 +2,24 @@
  * alertmanager.ts — API client for Alertmanager source operations.
  *
  * Covers: performAlertmanagerSourceAction, promoteAlertmanagerSource,
- *         stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback.
+ *         stopTrackingAlertmanagerSource, submitAlertmanagerRelevanceFeedback,
+ *         getAlertmanagerSourcesReviewPacket,
+ *         getAlertmanagerSourceDebugPacket,
+ *         getAlertmanagerSourcePromotionReview,
+ *         probeAlertmanagerSource.
  *
- * All operations use the generated OpenAPI client (IncidentsApi).
- * Request body types are generated from the backend API_ROUTES registry.
+ * All AlertManager-source operations are exposed through the generated
+ * ``AlertmanagerApi`` client. The contract guarantees that ``sourceId`` is
+ * transported as follows:
+ *
+ *   - ``performAlertmanagerSourceAction``: sourceId in the JSON request body.
+ *   - ``probeAlertmanagerSource``:          sourceId in the JSON request body.
+ *   - ``getAlertmanagerSourceDebugPacket``: sourceId as a required query param.
+ *   - ``getAlertmanagerSourcePromotionReview``: sourceId as a required query param.
+ *
+ * None of these operations place ``sourceId`` in the URL path, so opaque
+ * identifiers such as ``crd:monitoring/alertmanager-main`` round-trip
+ * end-to-end without URL encoding or manual unquote handling.
  *
  * Auth/session behavior: Uses generated client configuration with credentials: "include"
  * to preserve existing browser auth (cookies, session headers).
@@ -18,35 +32,35 @@ import type {
   AlertmanagerRelevanceFeedbackResponse,
 } from "../types";

-// Generated client imports
-import { IncidentsApi } from "../generated/k9b-api";
-import {
-  PerformAlertmanagerSourceActionRequest,
-  RecordAlertmanagerRelevanceFeedbackRequest,
-} from "../generated/k9b-api";
+// Generated client imports. AlertmanagerApi owns all AlertManager-source
+// operations; recordAlertmanagerRelevanceFeedback remains under IncidentsApi
+// since it is a feedback endpoint, not a source operation.
+import { AlertmanagerApi, IncidentsApi } from "../generated/k9b-api";
+import { RecordAlertmanagerRelevanceFeedbackRequest } from "../generated/k9b-api";
 import { createK9bApiConfiguration, normalizeGeneratedApiError } from "./generatedClient";

-// Body-based source_id endpoint (sourceId in request body to support slashes)
-const ALERTMANAGER_SOURCE_ACTION_ENDPOINT = "/api/runs/{runId}/alertmanager-sources/action";
-
 // =============================================================================
-// API Factory
+// API Factories
 // =============================================================================

+function createAlertmanagerApi(): AlertmanagerApi {
+  return new AlertmanagerApi(createK9bApiConfiguration());
+}
+
 function createIncidentsApi(): IncidentsApi {
   return new IncidentsApi(createK9bApiConfiguration());
 }

 // =============================================================================
-// AlertManager source action
+// AlertManager source action (sourceId in JSON body)
 // =============================================================================

 /**
  * Perform an action on an Alertmanager source.
  *
- * Uses direct fetch to POST to the body-based endpoint. sourceId is now in the
- * request body (not the URL path) to support slashes in identifiers like
- * 'crd:monitoring/kube-prometheus-stack-alertmanager'.
+ * The generated client exposes this operation on ``AlertmanagerApi``. The
+ * ``sourceId`` is sent in the JSON request body so opaque identifiers that
+ * contain ``/`` round-trip without URL encoding.
  *
  * @param request - The action request with sourceId, action, and optional clusterLabel/reason
  * @param runId - The run ID for the run-scoped route
@@ -56,32 +70,17 @@ export const performAlertmanagerSourceAction = async (
   runId: string
 ): Promise<AlertmanagerSourceActionResponse> => {
   try {
-    const config = createK9bApiConfiguration();
-    const endpoint = ALERTMANAGER_SOURCE_ACTION_ENDPOINT.replace("{runId}", runId);
-
-    const response = await fetch(`${config.basePath}${endpoint}`, {
-      method: "POST",
-      headers: {
-        "Content-Type": "application/json",
-        ...(config.username ? {
-          Authorization: `Basic ${btoa(`${config.username}:${config.password}`)}`
-        } : {}),
-      },
-      credentials: "include", // Preserve cookies/session
-      body: JSON.stringify({
+    const api = createAlertmanagerApi();
+    const result = await api.performAlertmanagerSourceAction({
+      runId,
+      performAlertmanagerSourceActionRequest: {
         sourceId: request.sourceId,
         action: request.action,
         clusterLabel: request.clusterLabel,
         reason: request.reason,
-      }),
+      },
     });
-
-    if (!response.ok) {
-      const errorBody = await response.text();
-      throw new Error(`HTTP ${response.status}: ${errorBody}`);
-    }
-
-    return await response.json() as AlertmanagerSourceActionResponse;
+    return result as AlertmanagerSourceActionResponse;
   } catch (error) {
     throw await normalizeGeneratedApiError(error);
   }
@@ -114,7 +113,94 @@ export const stopTrackingAlertmanagerSource = async (
 };

 // =============================================================================
-// AlertManager relevance feedback
+// AlertManager source debug packet (sourceId in required query param)
+// =============================================================================
+
+/**
+ * Fetch the debug packet for a single Alertmanager source.
+ *
+ * The ``sourceId`` is supplied as a required query parameter; the URL path
+ * does not include the source identifier, so slash-containing identifiers
+ * are accepted without any client-side URL encoding.
+ */
+export const getAlertmanagerSourceDebugPacket = async (
+  runId: string,
+  sourceId: string
+): Promise<unknown> => {
+  try {
+    const api = createAlertmanagerApi();
+    return await api.getAlertmanagerSourceDebugPacket({
+      runId,
+      sourceId,
+    });
+  } catch (error) {
+    throw await normalizeGeneratedApiError(error);
+  }
+};
+
+/**
+ * Live-probe an Alertmanager source and return the updated debug packet.
+ *
+ * The ``sourceId`` is sent in the JSON request body so the POST path stays
+ * stable regardless of the identifier content.
+ */
+export const probeAlertmanagerSource = async (
+  runId: string,
+  sourceId: string
+): Promise<unknown> => {
+  try {
+    const api = createAlertmanagerApi();
+    return await api.probeAlertmanagerSource({
+      runId,
+      probeAlertmanagerSourceRequest: { sourceId },
+    });
+  } catch (error) {
+    throw await normalizeGeneratedApiError(error);
+  }
+};
+
+// =============================================================================
+// AlertManager sources review and promotion-review packets
+// =============================================================================
+
+/**
+ * Fetch the multi-source review packet explaining why multiple Alertmanager
+ * sources were discovered for a run.
+ */
+export const getAlertmanagerSourcesReviewPacket = async (
+  runId: string
+): Promise<unknown> => {
+  try {
+    const api = createAlertmanagerApi();
+    return await api.getAlertmanagerSourcesReviewPacket({ runId });
+  } catch (error) {
+    throw await normalizeGeneratedApiError(error);
+  }
+};
+
+/**
+ * Fetch the pre-promotion review for a specific Alertmanager source.
+ *
+ * The ``sourceId`` is supplied as a required query parameter; the URL path
+ * does not include the source identifier.
+ */
+export const getAlertmanagerSourcePromotionReview = async (
+  runId: string,
+  sourceId: string
+): Promise<unknown> => {
+  try {
+    const api = createAlertmanagerApi();
+    return await api.getAlertmanagerSourcePromotionReview({
+      runId,
+      sourceId,
+    });
+  } catch (error) {
+    throw await normalizeGeneratedApiError(error);
+  }
+};
+
+// =============================================================================
+// AlertManager relevance feedback (non-source feedback endpoint)
 // =============================================================================

 /**

=== frontend/src/generated/k9b-api/.openapi-generator/FILES ===
diff --git a/frontend/src/generated/k9b-api/.openapi-generator/FILES b/frontend/src/generated/k9b-api/.openapi-generator/FILES
index 4b3b2f3..fc71b27 100644
--- a/frontend/src/generated/k9b-api/.openapi-generator/FILES
+++ b/frontend/src/generated/k9b-api/.openapi-generator/FILES
@@ -1,3 +1,4 @@
+apis/AlertmanagerApi.ts
 apis/AuthApi.ts
 apis/DiagnosisApi.ts
 apis/HealthApi.ts
@@ -5,6 +6,7 @@ apis/IncidentsApi.ts
 apis/OpenapiApi.ts
 apis/RuntimeApi.ts
 apis/index.ts
+docs/AlertmanagerApi.md
 docs/ApproveNextCheckRequest.md
 docs/AuthApi.md
 docs/CaptureIncidentSnapshot200Response.md
@@ -26,6 +28,7 @@ docs/OpenapiApi.md
 docs/PerformAlertmanagerSourceActionRequest.md
 docs/PostAuthLogin200Response.md
 docs/PostAuthLoginRequest.md
+docs/ProbeAlertmanagerSourceRequest.md
 docs/PromoteDeterministicNextCheckRequest.md
 docs/RecordAlertmanagerRelevanceFeedbackRequest.md
 docs/RecordNextCheckUsefulnessRequest.md
@@ -48,6 +51,7 @@ models/ListRuns200Response.ts
 models/PerformAlertmanagerSourceActionRequest.ts
 models/PostAuthLogin200Response.ts
 models/PostAuthLoginRequest.ts
+models/ProbeAlertmanagerSourceRequest.ts
 models/PromoteDeterministicNextCheckRequest.ts
 models/RecordAlertmanagerRelevanceFeedbackRequest.ts
 models/RecordNextCheckUsefulnessRequest.ts

=== frontend/src/generated/k9b-api/apis/AlertmanagerApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/AlertmanagerApi.ts b/frontend/src/generated/k9b-api/apis/AlertmanagerApi.ts
new file mode 100644
index 0000000..49ef4e4
--- /dev/null
+++ b/frontend/src/generated/k9b-api/apis/AlertmanagerApi.ts
@@ -0,0 +1,333 @@
+/* tslint:disable */
+/* eslint-disable */
+/**
+ * k9b API
+ * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
+ *
+ * The version of the OpenAPI document: 0.1.0
+ *
+ *
+ * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
+ * https://openapi-generator.tech
+ * Do not edit the class manually.
+ */
+
+import * as runtime from '../runtime';
+import {
+    type PerformAlertmanagerSourceActionRequest,
+    PerformAlertmanagerSourceActionRequestFromJSON,
+    PerformAlertmanagerSourceActionRequestToJSON,
+} from '../models/PerformAlertmanagerSourceActionRequest';
+import {
+    type ProbeAlertmanagerSourceRequest,
+    ProbeAlertmanagerSourceRequestFromJSON,
+    ProbeAlertmanagerSourceRequestToJSON,
+} from '../models/ProbeAlertmanagerSourceRequest';
+
+export interface GetAlertmanagerSourceDebugPacketRequest {
+    runId: string;
+    sourceId: string;
+}
+
+export interface GetAlertmanagerSourcePromotionReviewRequest {
+    runId: string;
+    sourceId: string;
+}
+
+export interface GetAlertmanagerSourcesReviewPacketRequest {
+    runId: string;
+}
+
+export interface PerformAlertmanagerSourceActionOperationRequest {
+    runId: string;
+    performAlertmanagerSourceActionRequest: PerformAlertmanagerSourceActionRequest;
+}
+
+export interface ProbeAlertmanagerSourceOperationRequest {
+    runId: string;
+    probeAlertmanagerSourceRequest: ProbeAlertmanagerSourceRequest;
+}
+
+/**
+ *
+ */
+export class AlertmanagerApi extends runtime.BaseAPI {
+
+    /**
+     * Creates request options for getAlertmanagerSourceDebugPacket without sending the request
+     */
+    async getAlertmanagerSourceDebugPacketRequestOpts(requestParameters: GetAlertmanagerSourceDebugPacketRequest): Promise<runtime.RequestOpts> {
+        if (requestParameters['runId'] == null) {
+            throw new runtime.RequiredError(
+                'runId',
+                'Required parameter "runId" was null or undefined when calling getAlertmanagerSourceDebugPacket().'
+            );
+        }
+
+        if (requestParameters['sourceId'] == null) {
+            throw new runtime.RequiredError(
+                'sourceId',
+                'Required parameter "sourceId" was null or undefined when calling getAlertmanagerSourceDebugPacket().'
+            );
+        }
+
+        const queryParameters: any = {};
+
+        if (requestParameters['sourceId'] != null) {
+            queryParameters['sourceId'] = requestParameters['sourceId'];
+        }
+
+        const headerParameters: runtime.HTTPHeaders = {};
+
+
+        let urlPath = `/api/runs/{run_id}/alertmanager-sources/debug-packet`;
+        urlPath = urlPath.replace('{run_id}', encodeURIComponent(String(requestParameters['runId'])));
+
+        return {
+            path: urlPath,
+            method: 'GET',
+            headers: headerParameters,
+            query: queryParameters,
+        };
+    }
+
+    /**
+     * Get a debug packet for a specific AlertManager source with probe and discovery details. The sourceId is supplied via the required ``sourceId`` query parameter so the URL path does not need to be slashed-encoded.
+     * Get AlertManager source debug packet
+     */
+    async getAlertmanagerSourceDebugPacketRaw(requestParameters: GetAlertmanagerSourceDebugPacketRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<object>> {
+        const requestOptions = await this.getAlertmanagerSourceDebugPacketRequestOpts(requestParameters);
+        const response = await this.request(requestOptions, initOverrides);
+
+        return new runtime.JSONApiResponse<any>(response);
+    }
+
+    /**
+     * Get a debug packet for a specific AlertManager source with probe and discovery details. The sourceId is supplied via the required ``sourceId`` query parameter so the URL path does not need to be slashed-encoded.
+     * Get AlertManager source debug packet
+     */
+    async getAlertmanagerSourceDebugPacket(requestParameters: GetAlertmanagerSourceDebugPacketRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<object> {
+        const response = await this.getAlertmanagerSourceDebugPacketRaw(requestParameters, initOverrides);
+        return await response.value();
+    }
+
+    /**
+     * Creates request options for getAlertmanagerSourcePromotionReview without sending the request
+     */
+    async getAlertmanagerSourcePromotionReviewRequestOpts(requestParameters: GetAlertmanagerSourcePromotionReviewRequest): Promise<runtime.RequestOpts> {
+        if (requestParameters['runId'] == null) {
+            throw new runtime.RequiredError(
+                'runId',
+                'Required parameter "runId" was null or undefined when calling getAlertmanagerSourcePromotionReview().'
+            );
+        }
+
+        if (requestParameters['sourceId'] == null) {
+            throw new runtime.RequiredError(
+                'sourceId',
+                'Required parameter "sourceId" was null or undefined when calling getAlertmanagerSourcePromotionReview().'
+            );
+        }
+
+        const queryParameters: any = {};
+
+        if (requestParameters['sourceId'] != null) {
+            queryParameters['sourceId'] = requestParameters['sourceId'];
+        }
+
+        const headerParameters: runtime.HTTPHeaders = {};
+
+
+        let urlPath = `/api/runs/{run_id}/alertmanager-sources/promotion-review`;
+        urlPath = urlPath.replace('{run_id}', encodeURIComponent(String(requestParameters['runId'])));
+
+        return {
+            path: urlPath,
+            method: 'GET',
+            headers: headerParameters,
+            query: queryParameters,
+        };
+    }
+
+    /**
+     * Get a pre-promotion review assessing risk before promoting a source to manual. The sourceId is supplied via the required ``sourceId`` query parameter so the URL path does not need to be slashed-encoded.
+     * Get AlertManager source promotion review
+     */
+    async getAlertmanagerSourcePromotionReviewRaw(requestParameters: GetAlertmanagerSourcePromotionReviewRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<object>> {
+        const requestOptions = await this.getAlertmanagerSourcePromotionReviewRequestOpts(requestParameters);
+        const response = await this.request(requestOptions, initOverrides);
+
+        return new runtime.JSONApiResponse<any>(response);
+    }
+
+    /**
+     * Get a pre-promotion review assessing risk before promoting a source to manual. The sourceId is supplied via the required ``sourceId`` query parameter so the URL path does not need to be slashed-encoded.
+     * Get AlertManager source promotion review
+     */
+    async getAlertmanagerSourcePromotionReview(requestParameters: GetAlertmanagerSourcePromotionReviewRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<object> {
+        const response = await this.getAlertmanagerSourcePromotionReviewRaw(requestParameters, initOverrides);
+        return await response.value();
+    }
+
+    /**
+     * Creates request options for getAlertmanagerSourcesReviewPacket without sending the request
+     */
+    async getAlertmanagerSourcesReviewPacketRequestOpts(requestParameters: GetAlertmanagerSourcesReviewPacketRequest): Promise<runtime.RequestOpts> {
+        if (requestParameters['runId'] == null) {
+            throw new runtime.RequiredError(
+                'runId',
+                'Required parameter "runId" was null or undefined when calling getAlertmanagerSourcesReviewPacket().'
+            );
+        }
+
+        const queryParameters: any = {};
+
+        const headerParameters: runtime.HTTPHeaders = {};
+
+
+        let urlPath = `/api/runs/{run_id}/alertmanager-sources/review-packet`;
+        urlPath = urlPath.replace('{run_id}', encodeURIComponent(String(requestParameters['runId'])));
+
+        return {
+            path: urlPath,
+            method: 'GET',
+            headers: headerParameters,
+            query: queryParameters,
+        };
+    }
+
+    /**
+     * Get the review packet explaining why multiple AlertManager sources were discovered.
+     * Get AlertManager sources review packet
+     */
+    async getAlertmanagerSourcesReviewPacketRaw(requestParameters: GetAlertmanagerSourcesReviewPacketRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<object>> {
+        const requestOptions = await this.getAlertmanagerSourcesReviewPacketRequestOpts(requestParameters);
+        const response = await this.request(requestOptions, initOverrides);
+
+        return new runtime.JSONApiResponse<any>(response);
+    }
+
+    /**
+     * Get the review packet explaining why multiple AlertManager sources were discovered.
+     * Get AlertManager sources review packet
+     */
+    async getAlertmanagerSourcesReviewPacket(requestParameters: GetAlertmanagerSourcesReviewPacketRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<object> {
+        const response = await this.getAlertmanagerSourcesReviewPacketRaw(requestParameters, initOverrides);
+        return await response.value();
+    }
+
+    /**
+     * Creates request options for performAlertmanagerSourceAction without sending the request
+     */
+    async performAlertmanagerSourceActionRequestOpts(requestParameters: PerformAlertmanagerSourceActionOperationRequest): Promise<runtime.RequestOpts> {
+        if (requestParameters['runId'] == null) {
+            throw new runtime.RequiredError(
+                'runId',
+                'Required parameter "runId" was null or undefined when calling performAlertmanagerSourceAction().'
+            );
+        }
+
+        if (requestParameters['performAlertmanagerSourceActionRequest'] == null) {
+            throw new runtime.RequiredError(
+                'performAlertmanagerSourceActionRequest',
+                'Required parameter "performAlertmanagerSourceActionRequest" was null or undefined when calling performAlertmanagerSourceAction().'
+            );
+        }
+
+        const queryParameters: any = {};
+
+        const headerParameters: runtime.HTTPHeaders = {};
+
+        headerParameters['Content-Type'] = 'application/json';
+
+
+        let urlPath = `/api/runs/{run_id}/alertmanager-sources/action`;
+        urlPath = urlPath.replace('{run_id}', encodeURIComponent(String(requestParameters['runId'])));
+
+        return {
+            path: urlPath,
+            method: 'POST',
+            headers: headerParameters,
+            query: queryParameters,
+            body: PerformAlertmanagerSourceActionRequestToJSON(requestParameters['performAlertmanagerSourceActionRequest']),
+        };
+    }
+
+    /**
+     * Perform an action (promote/disable) on an AlertManager source. The sourceId is transported in the JSON request body so opaque identifiers that contain \'/\' do not need URL encoding.
+     * Perform AlertManager source action
+     */
+    async performAlertmanagerSourceActionRaw(requestParameters: PerformAlertmanagerSourceActionOperationRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<object>> {
+        const requestOptions = await this.performAlertmanagerSourceActionRequestOpts(requestParameters);
+        const response = await this.request(requestOptions, initOverrides);
+
+        return new runtime.JSONApiResponse<any>(response);
+    }
+
+    /**
+     * Perform an action (promote/disable) on an AlertManager source. The sourceId is transported in the JSON request body so opaque identifiers that contain \'/\' do not need URL encoding.
+     * Perform AlertManager source action
+     */
+    async performAlertmanagerSourceAction(requestParameters: PerformAlertmanagerSourceActionOperationRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<object> {
+        const response = await this.performAlertmanagerSourceActionRaw(requestParameters, initOverrides);
+        return await response.value();
+    }
+
+    /**
+     * Creates request options for probeAlertmanagerSource without sending the request
+     */
+    async probeAlertmanagerSourceRequestOpts(requestParameters: ProbeAlertmanagerSourceOperationRequest): Promise<runtime.RequestOpts> {
+        if (requestParameters['runId'] == null) {
+            throw new runtime.RequiredError(
+                'runId',
+                'Required parameter "runId" was null or undefined when calling probeAlertmanagerSource().'
+            );
+        }
+
+        if (requestParameters['probeAlertmanagerSourceRequest'] == null) {
+            throw new runtime.RequiredError(
+                'probeAlertmanagerSourceRequest',
+                'Required parameter "probeAlertmanagerSourceRequest" was null or undefined when calling probeAlertmanagerSource().'
+            );
+        }
+
+        const queryParameters: any = {};
+
+        const headerParameters: runtime.HTTPHeaders = {};
+
+        headerParameters['Content-Type'] = 'application/json';
+
+
+        let urlPath = `/api/runs/{run_id}/alertmanager-sources/debug-packet/probe`;
+        urlPath = urlPath.replace('{run_id}', encodeURIComponent(String(requestParameters['runId'])));
+
+        return {
+            path: urlPath,
+            method: 'POST',
+            headers: headerParameters,
+            query: queryParameters,
+            body: ProbeAlertmanagerSourceRequestToJSON(requestParameters['probeAlertmanagerSourceRequest']),
+        };
+    }
+
+    /**
+     * Run a live probe on the AlertManager source and return the updated debug packet. The sourceId is supplied in the JSON request body.
+     * Probe AlertManager source now
+     */
+    async probeAlertmanagerSourceRaw(requestParameters: ProbeAlertmanagerSourceOperationRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<object>> {
+        const requestOptions = await this.probeAlertmanagerSourceRequestOpts(requestParameters);
+        const response = await this.request(requestOptions, initOverrides);
+
+        return new runtime.JSONApiResponse<any>(response);
+    }
+
+    /**
+     * Run a live probe on the AlertManager source and return the updated debug packet. The sourceId is supplied in the JSON request body.
+     * Probe AlertManager source now
+     */
+    async probeAlertmanagerSource(requestParameters: ProbeAlertmanagerSourceOperationRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<object> {
+        const response = await this.probeAlertmanagerSourceRaw(requestParameters, initOverrides);
+        return await response.value();
+    }
+
+}

=== frontend/src/generated/k9b-api/apis/AuthApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/AuthApi.ts b/frontend/src/generated/k9b-api/apis/AuthApi.ts
index 443ef63..18f164a 100644
--- a/frontend/src/generated/k9b-api/apis/AuthApi.ts
+++ b/frontend/src/generated/k9b-api/apis/AuthApi.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -39,7 +39,7 @@ export interface PostAuthLoginOperationRequest {
 }

 /**
- *
+ *
  */
 export class AuthApi extends runtime.BaseAPI {


=== frontend/src/generated/k9b-api/apis/DiagnosisApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/DiagnosisApi.ts b/frontend/src/generated/k9b-api/apis/DiagnosisApi.ts
index 5db489f..935c4ef 100644
--- a/frontend/src/generated/k9b-api/apis/DiagnosisApi.ts
+++ b/frontend/src/generated/k9b-api/apis/DiagnosisApi.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -31,7 +31,7 @@ export interface RunIncidentOnePassDiagnosisRequest {
 }

 /**
- *
+ *
  */
 export class DiagnosisApi extends runtime.BaseAPI {


=== frontend/src/generated/k9b-api/apis/HealthApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/HealthApi.ts b/frontend/src/generated/k9b-api/apis/HealthApi.ts
index 7fb4dc2..26087c5 100644
--- a/frontend/src/generated/k9b-api/apis/HealthApi.ts
+++ b/frontend/src/generated/k9b-api/apis/HealthApi.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -25,7 +25,7 @@ import {
 } from '../models/GetHealthDetails200Response';

 /**
- *
+ *
  */
 export class HealthApi extends runtime.BaseAPI {


=== frontend/src/generated/k9b-api/apis/IncidentsApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/IncidentsApi.ts b/frontend/src/generated/k9b-api/apis/IncidentsApi.ts
index 0526c9a..3830181 100644
--- a/frontend/src/generated/k9b-api/apis/IncidentsApi.ts
+++ b/frontend/src/generated/k9b-api/apis/IncidentsApi.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -58,11 +58,6 @@ import {
     ListRuns200ResponseFromJSON,
     ListRuns200ResponseToJSON,
 } from '../models/ListRuns200Response';
-import {
-    type PerformAlertmanagerSourceActionRequest,
-    PerformAlertmanagerSourceActionRequestFromJSON,
-    PerformAlertmanagerSourceActionRequestToJSON,
-} from '../models/PerformAlertmanagerSourceActionRequest';
 import {
     type PromoteDeterministicNextCheckRequest,
     PromoteDeterministicNextCheckRequestFromJSON,
@@ -136,12 +131,6 @@ export interface ListRunsRequest {
     clusterLabel?: string;
 }

-export interface PerformAlertmanagerSourceActionOperationRequest {
-    runId: string;
-    sourceId: string;
-    performAlertmanagerSourceActionRequest: PerformAlertmanagerSourceActionRequest;
-}
-
 export interface PromoteDeterministicNextCheckOperationRequest {
     promoteDeterministicNextCheckRequest: PromoteDeterministicNextCheckRequest;
 }
@@ -171,7 +160,7 @@ export interface RunIncidentOnePassDiagnosisRequest {
 }

 /**
- *
+ *
  */
 export class IncidentsApi extends runtime.BaseAPI {

@@ -790,71 +779,6 @@ export class IncidentsApi extends runtime.BaseAPI {
         return await response.value();
     }

-    /**
-     * Creates request options for performAlertmanagerSourceAction without sending the request
-     */
-    async performAlertmanagerSourceActionRequestOpts(requestParameters: PerformAlertmanagerSourceActionOperationRequest): Promise<runtime.RequestOpts> {
-        if (requestParameters['runId'] == null) {
-            throw new runtime.RequiredError(
-                'runId',
-                'Required parameter "runId" was null or undefined when calling performAlertmanagerSourceAction().'
-            );
-        }
-
-        if (requestParameters['sourceId'] == null) {
-            throw new runtime.RequiredError(
-                'sourceId',
-                'Required parameter "sourceId" was null or undefined when calling performAlertmanagerSourceAction().'
-            );
-        }
-
-        if (requestParameters['performAlertmanagerSourceActionRequest'] == null) {
-            throw new runtime.RequiredError(
-                'performAlertmanagerSourceActionRequest',
-                'Required parameter "performAlertmanagerSourceActionRequest" was null or undefined when calling performAlertmanagerSourceAction().'
-            );
-        }
-
-        const queryParameters: any = {};
-
-        const headerParameters: runtime.HTTPHeaders = {};
-
-        headerParameters['Content-Type'] = 'application/json';
-
-
-        let urlPath = `/api/runs/{run_id}/alertmanager-sources/{source_id}/action`;
-        urlPath = urlPath.replace('{run_id}', encodeURIComponent(String(requestParameters['runId'])));
-        urlPath = urlPath.replace('{source_id}', encodeURIComponent(String(requestParameters['sourceId'])));
-
-        return {
-            path: urlPath,
-            method: 'POST',
-            headers: headerParameters,
-            query: queryParameters,
-            body: PerformAlertmanagerSourceActionRequestToJSON(requestParameters['performAlertmanagerSourceActionRequest']),
-        };
-    }
-
-    /**
-     * Perform an action (promote/disable) on an AlertManager source.
-     * Perform AlertManager source action
-     */
-    async performAlertmanagerSourceActionRaw(requestParameters: PerformAlertmanagerSourceActionOperationRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<runtime.ApiResponse<object>> {
-        const requestOptions = await this.performAlertmanagerSourceActionRequestOpts(requestParameters);
-        const response = await this.request(requestOptions, initOverrides);
-
-        return new runtime.JSONApiResponse<any>(response);
-    }
-
-    /**
-     * Perform an action (promote/disable) on an AlertManager source.
-     * Perform AlertManager source action
-     */
-    async performAlertmanagerSourceAction(requestParameters: PerformAlertmanagerSourceActionOperationRequest, initOverrides?: RequestInit | runtime.InitOverrideFunction): Promise<object> {
-        const response = await this.performAlertmanagerSourceActionRaw(requestParameters, initOverrides);
-        return await response.value();
-    }
-
     /**
      * Creates request options for promoteDeterministicNextCheck without sending the request
      */

=== frontend/src/generated/k9b-api/apis/OpenapiApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/OpenapiApi.ts b/frontend/src/generated/k9b-api/apis/OpenapiApi.ts
index 4d2d36f..57933ba 100644
--- a/frontend/src/generated/k9b-api/apis/OpenapiApi.ts
+++ b/frontend/src/generated/k9b-api/apis/OpenapiApi.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -15,7 +15,7 @@
 import * as runtime from '../runtime';

 /**
- *
+ *
  */
 export class OpenapiApi extends runtime.BaseAPI {


=== frontend/src/generated/k9b-api/apis/RuntimeApi.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/RuntimeApi.ts b/frontend/src/generated/k9b-api/apis/RuntimeApi.ts
index aa79e96..f586e0a 100644
--- a/frontend/src/generated/k9b-api/apis/RuntimeApi.ts
+++ b/frontend/src/generated/k9b-api/apis/RuntimeApi.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -15,7 +15,7 @@
 import * as runtime from '../runtime';

 /**
- *
+ *
  */
 export class RuntimeApi extends runtime.BaseAPI {


=== frontend/src/generated/k9b-api/apis/index.ts ===
diff --git a/frontend/src/generated/k9b-api/apis/index.ts b/frontend/src/generated/k9b-api/apis/index.ts
index 62654d6..04e5c00 100644
--- a/frontend/src/generated/k9b-api/apis/index.ts
+++ b/frontend/src/generated/k9b-api/apis/index.ts
@@ -1,5 +1,6 @@
 /* tslint:disable */
 /* eslint-disable */
+export * from './AlertmanagerApi';
 export * from './AuthApi';
 export * from './DiagnosisApi';
 export * from './HealthApi';

=== frontend/src/generated/k9b-api/docs/AlertmanagerApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/AlertmanagerApi.md b/frontend/src/generated/k9b-api/docs/AlertmanagerApi.md
new file mode 100644
index 0000000..342c81b
--- /dev/null
+++ b/frontend/src/generated/k9b-api/docs/AlertmanagerApi.md
@@ -0,0 +1,359 @@
+# AlertmanagerApi
+
+All URIs are relative to *http://localhost*
+
+| Method | HTTP request | Description |
+|------------- | ------------- | -------------|
+| [**getAlertmanagerSourceDebugPacket**](AlertmanagerApi.md#getalertmanagersourcedebugpacket) | **GET** /api/runs/{run_id}/alertmanager-sources/debug-packet | Get AlertManager source debug packet |
+| [**getAlertmanagerSourcePromotionReview**](AlertmanagerApi.md#getalertmanagersourcepromotionreview) | **GET** /api/runs/{run_id}/alertmanager-sources/promotion-review | Get AlertManager source promotion review |
+| [**getAlertmanagerSourcesReviewPacket**](AlertmanagerApi.md#getalertmanagersourcesreviewpacket) | **GET** /api/runs/{run_id}/alertmanager-sources/review-packet | Get AlertManager sources review packet |
+| [**performAlertmanagerSourceAction**](AlertmanagerApi.md#performalertmanagersourceactionoperation) | **POST** /api/runs/{run_id}/alertmanager-sources/action | Perform AlertManager source action |
+| [**probeAlertmanagerSource**](AlertmanagerApi.md#probealertmanagersourceoperation) | **POST** /api/runs/{run_id}/alertmanager-sources/debug-packet/probe | Probe AlertManager source now |
+
+
+
+## getAlertmanagerSourceDebugPacket
+
+> object getAlertmanagerSourceDebugPacket(runId, sourceId)
+
+Get AlertManager source debug packet
+
+Get a debug packet for a specific AlertManager source with probe and discovery details. The sourceId is supplied via the required &#x60;&#x60;sourceId&#x60;&#x60; query parameter so the URL path does not need to be slashed-encoded.
+
+### Example
+
+```ts
+import {
+  Configuration,
+  AlertmanagerApi,
+} from '';
+import type { GetAlertmanagerSourceDebugPacketRequest } from '';
+
+async function example() {
+  console.log("🚀 Testing  SDK...");
+  const api = new AlertmanagerApi();
+
+  const body = {
+    // string
+    runId: runId_example,
+    // string
+    sourceId: sourceId_example,
+  } satisfies GetAlertmanagerSourceDebugPacketRequest;
+
+  try {
+    const data = await api.getAlertmanagerSourceDebugPacket(body);
+    console.log(data);
+  } catch (error) {
+    console.error(error);
+  }
+}
+
+// Run the test
+example().catch(console.error);
+```
+
+### Parameters
+
+
+| Name | Type | Description  | Notes |
+|------------- | ------------- | ------------- | -------------|
+| **runId** | `string` |  | [Defaults to `undefined`] |
+| **sourceId** | `string` |  | [Defaults to `undefined`] |
+
+### Return type
+
+**object**
+
+### Authorization
+
+No authorization required
+
+### HTTP request headers
+
+- **Content-Type**: Not defined
+- **Accept**: `application/json`
+
+
+### HTTP response details
+| Status code | Description | Response headers |
+|-------------|-------------|------------------|
+| **200** | Debug packet generated |  -  |
+
+[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
+
+
+## getAlertmanagerSourcePromotionReview
+
+> object getAlertmanagerSourcePromotionReview(runId, sourceId)
+
+Get AlertManager source promotion review
+
+Get a pre-promotion review assessing risk before promoting a source to manual. The sourceId is supplied via the required &#x60;&#x60;sourceId&#x60;&#x60; query parameter so the URL path does not need to be slashed-encoded.
+
+### Example
+
+```ts
+import {
+  Configuration,
+  AlertmanagerApi,
+} from '';
+import type { GetAlertmanagerSourcePromotionReviewRequest } from '';
+
+async function example() {
+  console.log("🚀 Testing  SDK...");
+  const api = new AlertmanagerApi();
+
+  const body = {
+    // string
+    runId: runId_example,
+    // string
+    sourceId: sourceId_example,
+  } satisfies GetAlertmanagerSourcePromotionReviewRequest;
+
+  try {
+    const data = await api.getAlertmanagerSourcePromotionReview(body);
+    console.log(data);
+  } catch (error) {
+    console.error(error);
+  }
+}
+
+// Run the test
+example().catch(console.error);
+```
+
+### Parameters
+
+
+| Name | Type | Description  | Notes |
+|------------- | ------------- | ------------- | -------------|
+| **runId** | `string` |  | [Defaults to `undefined`] |
+| **sourceId** | `string` |  | [Defaults to `undefined`] |
+
+### Return type
+
+**object**
+
+### Authorization
+
+No authorization required
+
+### HTTP request headers
+
+- **Content-Type**: Not defined
+- **Accept**: `application/json`
+
+
+### HTTP response details
+| Status code | Description | Response headers |
+|-------------|-------------|------------------|
+| **200** | Promotion review generated |  -  |
+
+[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
+
+
+## getAlertmanagerSourcesReviewPacket
+
+> object getAlertmanagerSourcesReviewPacket(runId)
+
+Get AlertManager sources review packet
+
+Get the review packet explaining why multiple AlertManager sources were discovered.
+
+### Example
+
+```ts
+import {
+  Configuration,
+  AlertmanagerApi,
+} from '';
+import type { GetAlertmanagerSourcesReviewPacketRequest } from '';
+
+async function example() {
+  console.log("🚀 Testing  SDK...");
+  const api = new AlertmanagerApi();
+
+  const body = {
+    // string
+    runId: runId_example,
+  } satisfies GetAlertmanagerSourcesReviewPacketRequest;
+
+  try {
+    const data = await api.getAlertmanagerSourcesReviewPacket(body);
+    console.log(data);
+  } catch (error) {
+    console.error(error);
+  }
+}
+
+// Run the test
+example().catch(console.error);
+```
+
+### Parameters
+
+
+| Name | Type | Description  | Notes |
+|------------- | ------------- | ------------- | -------------|
+| **runId** | `string` |  | [Defaults to `undefined`] |
+
+### Return type
+
+**object**
+
+### Authorization
+
+No authorization required
+
+### HTTP request headers
+
+- **Content-Type**: Not defined
+- **Accept**: `application/json`
+
+
+### HTTP response details
+| Status code | Description | Response headers |
+|-------------|-------------|------------------|
+| **200** | Review packet generated |  -  |
+
+[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
+
+
+## performAlertmanagerSourceAction
+
+> object performAlertmanagerSourceAction(runId, performAlertmanagerSourceActionRequest)
+
+Perform AlertManager source action
+
+Perform an action (promote/disable) on an AlertManager source. The sourceId is transported in the JSON request body so opaque identifiers that contain \&#39;/\&#39; do not need URL encoding.
+
+### Example
+
+```ts
+import {
+  Configuration,
+  AlertmanagerApi,
+} from '';
+import type { PerformAlertmanagerSourceActionOperationRequest } from '';
+
+async function example() {
+  console.log("🚀 Testing  SDK...");
+  const api = new AlertmanagerApi();
+
+  const body = {
+    // string
+    runId: runId_example,
+    // PerformAlertmanagerSourceActionRequest
+    performAlertmanagerSourceActionRequest: ...,
+  } satisfies PerformAlertmanagerSourceActionOperationRequest;
+
+  try {
+    const data = await api.performAlertmanagerSourceAction(body);
+    console.log(data);
+  } catch (error) {
+    console.error(error);
+  }
+}
+
+// Run the test
+example().catch(console.error);
+```
+
+### Parameters
+
+
+| Name | Type | Description  | Notes |
+|------------- | ------------- | ------------- | -------------|
+| **runId** | `string` |  | [Defaults to `undefined`] |
+| **performAlertmanagerSourceActionRequest** | [PerformAlertmanagerSourceActionRequest](PerformAlertmanagerSourceActionRequest.md) |  | |
+
+### Return type
+
+**object**
+
+### Authorization
+
+No authorization required
+
+### HTTP request headers
+
+- **Content-Type**: `application/json`
+- **Accept**: `application/json`
+
+
+### HTTP response details
+| Status code | Description | Response headers |
+|-------------|-------------|------------------|
+| **200** | Action performed |  -  |
+
+[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
+
+
+## probeAlertmanagerSource
+
+> object probeAlertmanagerSource(runId, probeAlertmanagerSourceRequest)
+
+Probe AlertManager source now
+
+Run a live probe on the AlertManager source and return the updated debug packet. The sourceId is supplied in the JSON request body.
+
+### Example
+
+```ts
+import {
+  Configuration,
+  AlertmanagerApi,
+} from '';
+import type { ProbeAlertmanagerSourceOperationRequest } from '';
+
+async function example() {
+  console.log("🚀 Testing  SDK...");
+  const api = new AlertmanagerApi();
+
+  const body = {
+    // string
+    runId: runId_example,
+    // ProbeAlertmanagerSourceRequest
+    probeAlertmanagerSourceRequest: ...,
+  } satisfies ProbeAlertmanagerSourceOperationRequest;
+
+  try {
+    const data = await api.probeAlertmanagerSource(body);
+    console.log(data);
+  } catch (error) {
+    console.error(error);
+  }
+}
+
+// Run the test
+example().catch(console.error);
+```
+
+### Parameters
+
+
+| Name | Type | Description  | Notes |
+|------------- | ------------- | ------------- | -------------|
+| **runId** | `string` |  | [Defaults to `undefined`] |
+| **probeAlertmanagerSourceRequest** | [ProbeAlertmanagerSourceRequest](ProbeAlertmanagerSourceRequest.md) |  | |
+
+### Return type
+
+**object**
+
+### Authorization
+
+No authorization required
+
+### HTTP request headers
+
+- **Content-Type**: `application/json`
+- **Accept**: `application/json`
+
+
+### HTTP response details
+| Status code | Description | Response headers |
+|-------------|-------------|------------------|
+| **200** | Probe completed |  -  |
+
+[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

=== frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md b/frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md
index 9eca226..31acd79 100644
--- a/frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md
+++ b/frontend/src/generated/k9b-api/docs/ApproveNextCheckRequest.md
@@ -35,5 +35,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/AuthApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/AuthApi.md b/frontend/src/generated/k9b-api/docs/AuthApi.md
index 30fcc5a..79388fe 100644
--- a/frontend/src/generated/k9b-api/docs/AuthApi.md
+++ b/frontend/src/generated/k9b-api/docs/AuthApi.md
@@ -254,4 +254,3 @@ No authorization required
 | **200** | Logout successful |  -  |

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-

=== frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md b/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md
index c15e9e5..2e07062 100644
--- a/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md
+++ b/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshot200Response.md
@@ -32,5 +32,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md b/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md
index 903e95e..90840ee 100644
--- a/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md
+++ b/frontend/src/generated/k9b-api/docs/CaptureIncidentSnapshotRequest.md
@@ -33,5 +33,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md b/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md
index b8faf23..e565c28 100644
--- a/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md
+++ b/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacket200Response.md
@@ -32,5 +32,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md b/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md
index e065a6b..4f9cbc3 100644
--- a/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md
+++ b/frontend/src/generated/k9b-api/docs/CreateIncidentReviewPacketRequest.md
@@ -33,5 +33,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/DiagnosisApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/DiagnosisApi.md b/frontend/src/generated/k9b-api/docs/DiagnosisApi.md
index 3c5756a..d75d5e9 100644
--- a/frontend/src/generated/k9b-api/docs/DiagnosisApi.md
+++ b/frontend/src/generated/k9b-api/docs/DiagnosisApi.md
@@ -278,4 +278,3 @@ No authorization required
 | **200** | Diagnosis completed |  -  |

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-

=== frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md b/frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md
index 8313d40..412088f 100644
--- a/frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md
+++ b/frontend/src/generated/k9b-api/docs/ExecuteNextCheckRequest.md
@@ -37,5 +37,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md b/frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md
index 00e41b5..42673f3 100644
--- a/frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md
+++ b/frontend/src/generated/k9b-api/docs/GetAuthMe200Response.md
@@ -33,5 +33,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md b/frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md
index 2fc3a49..2ee1f70 100644
--- a/frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md
+++ b/frontend/src/generated/k9b-api/docs/GetAuthStatus200Response.md
@@ -33,5 +33,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/GetHealth200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/GetHealth200Response.md b/frontend/src/generated/k9b-api/docs/GetHealth200Response.md
index 0f06ec3..f294e1e 100644
--- a/frontend/src/generated/k9b-api/docs/GetHealth200Response.md
+++ b/frontend/src/generated/k9b-api/docs/GetHealth200Response.md
@@ -32,5 +32,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md b/frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md
index 68954c1..fc6ca5c 100644
--- a/frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md
+++ b/frontend/src/generated/k9b-api/docs/GetHealthDetails200Response.md
@@ -35,5 +35,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/HealthApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/HealthApi.md b/frontend/src/generated/k9b-api/docs/HealthApi.md
index 41f9647..a2ab53a 100644
--- a/frontend/src/generated/k9b-api/docs/HealthApi.md
+++ b/frontend/src/generated/k9b-api/docs/HealthApi.md
@@ -126,4 +126,3 @@ No authorization required
 | **200** | Health details |  -  |

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-

=== frontend/src/generated/k9b-api/docs/IncidentsApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/IncidentsApi.md b/frontend/src/generated/k9b-api/docs/IncidentsApi.md
index a3c2b9d..1e99ef2 100644
--- a/frontend/src/generated/k9b-api/docs/IncidentsApi.md
+++ b/frontend/src/generated/k9b-api/docs/IncidentsApi.md
@@ -17,7 +17,6 @@ All URIs are relative to *http://localhost*
 | [**listIncidents**](IncidentsApi.md#listincidents) | **GET** /api/incidents | List incidents |
 | [**listNotifications**](IncidentsApi.md#listnotifications) | **GET** /api/notifications | List notifications |
 | [**listRuns**](IncidentsApi.md#listruns) | **GET** /api/runs | List runs |
-| [**performAlertmanagerSourceAction**](IncidentsApi.md#performalertmanagersourceactionoperation) | **POST** /api/runs/{run_id}/alertmanager-sources/{source_id}/action | Perform AlertManager source action |
 | [**promoteDeterministicNextCheck**](IncidentsApi.md#promotedeterministicnextcheckoperation) | **POST** /api/deterministic-next-check/promote | Promote deterministic next-check |
 | [**recordAlertmanagerRelevanceFeedback**](IncidentsApi.md#recordalertmanagerrelevancefeedbackoperation) | **POST** /api/alertmanager-relevance-feedback | Record AlertManager relevance feedback |
 | [**recordNextCheckUsefulness**](IncidentsApi.md#recordnextcheckusefulnessoperation) | **POST** /api/next-check-execution-usefulness | Record next-check usefulness feedback |
@@ -909,79 +908,6 @@ No authorization required
 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


-## performAlertmanagerSourceAction
-
-> object performAlertmanagerSourceAction(runId, sourceId, performAlertmanagerSourceActionRequest)
-
-Perform AlertManager source action
-
-Perform an action (promote/disable) on an AlertManager source.
-
-### Example
-
-```ts
-import {
-  Configuration,
-  IncidentsApi,
-} from '';
-import type { PerformAlertmanagerSourceActionOperationRequest } from '';
-
-async function example() {
-  console.log("🚀 Testing  SDK...");
-  const api = new IncidentsApi();
-
-  const body = {
-    // string
-    runId: runId_example,
-    // string
-    sourceId: sourceId_example,
-    // PerformAlertmanagerSourceActionRequest
-    performAlertmanagerSourceActionRequest: ...,
-  } satisfies PerformAlertmanagerSourceActionOperationRequest;
-
-  try {
-    const data = await api.performAlertmanagerSourceAction(body);
-    console.log(data);
-  } catch (error) {
-    console.error(error);
-  }
-}
-
-// Run the test
-example().catch(console.error);
-```
-
-### Parameters
-
-
-| Name | Type | Description  | Notes |
-|------------- | ------------- | ------------- | -------------|
-| **runId** | `string` |  | [Defaults to `undefined`] |
-| **sourceId** | `string` |  | [Defaults to `undefined`] |
-| **performAlertmanagerSourceActionRequest** | [PerformAlertmanagerSourceActionRequest](PerformAlertmanagerSourceActionRequest.md) |  | |
-
-### Return type
-
-**object**
-
-### Authorization
-
-No authorization required
-
-### HTTP request headers
-
-- **Content-Type**: `application/json`
-- **Accept**: `application/json`
-
-
-### HTTP response details
-| Status code | Description | Response headers |
-|-------------|-------------|------------------|
-| **200** | Action performed |  -  |
-
-[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-
 ## promoteDeterministicNextCheck

 > object promoteDeterministicNextCheck(promoteDeterministicNextCheckRequest)
@@ -1449,4 +1375,3 @@ No authorization required
 | **200** | Diagnosis completed |  -  |

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-

=== frontend/src/generated/k9b-api/docs/ListIncidents200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/ListIncidents200Response.md b/frontend/src/generated/k9b-api/docs/ListIncidents200Response.md
index 41bdd2d..674f58a 100644
--- a/frontend/src/generated/k9b-api/docs/ListIncidents200Response.md
+++ b/frontend/src/generated/k9b-api/docs/ListIncidents200Response.md
@@ -32,5 +32,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/ListNotifications200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/ListNotifications200Response.md b/frontend/src/generated/k9b-api/docs/ListNotifications200Response.md
index 41787fe..4417ac4 100644
--- a/frontend/src/generated/k9b-api/docs/ListNotifications200Response.md
+++ b/frontend/src/generated/k9b-api/docs/ListNotifications200Response.md
@@ -32,5 +32,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/ListRuns200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/ListRuns200Response.md b/frontend/src/generated/k9b-api/docs/ListRuns200Response.md
index dcb6242..7258261 100644
--- a/frontend/src/generated/k9b-api/docs/ListRuns200Response.md
+++ b/frontend/src/generated/k9b-api/docs/ListRuns200Response.md
@@ -32,5 +32,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/OpenapiApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/OpenapiApi.md b/frontend/src/generated/k9b-api/docs/OpenapiApi.md
index 1183812..345925c 100644
--- a/frontend/src/generated/k9b-api/docs/OpenapiApi.md
+++ b/frontend/src/generated/k9b-api/docs/OpenapiApi.md
@@ -125,4 +125,3 @@ No authorization required
 | **200** | OpenAPI 3.1 schema |  -  |

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-

=== frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md b/frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md
index 5bdae88..cf9a1ce 100644
--- a/frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md
+++ b/frontend/src/generated/k9b-api/docs/PerformAlertmanagerSourceActionRequest.md
@@ -1,7 +1,7 @@

 # PerformAlertmanagerSourceActionRequest

-AlertManager source action request
+AlertManager source action request. sourceId is in body to support slashes in identifiers.

 ## Properties

@@ -10,6 +10,7 @@ Name | Type
 `action` | string
 `clusterLabel` | string
 `reason` | string
+`sourceId` | string

 ## Example

@@ -21,6 +22,7 @@ const example = {
   "action": null,
   "clusterLabel": null,
   "reason": null,
+  "sourceId": null,
 } satisfies PerformAlertmanagerSourceActionRequest

 console.log(example)
@@ -35,5 +37,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md ===
diff --git a/frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md b/frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md
index a80de4c..3d878b7 100644
--- a/frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md
+++ b/frontend/src/generated/k9b-api/docs/PostAuthLogin200Response.md
@@ -30,5 +30,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md b/frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md
index 781ad8f..9c54567 100644
--- a/frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md
+++ b/frontend/src/generated/k9b-api/docs/PostAuthLoginRequest.md
@@ -33,5 +33,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/ProbeAlertmanagerSourceRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/ProbeAlertmanagerSourceRequest.md b/frontend/src/generated/k9b-api/docs/ProbeAlertmanagerSourceRequest.md
new file mode 100644
index 0000000..460dc1f
--- /dev/null
+++ b/frontend/src/generated/k9b-api/docs/ProbeAlertmanagerSourceRequest.md
@@ -0,0 +1,33 @@
+
+# ProbeAlertmanagerSourceRequest
+
+AlertManager source probe request. sourceId is in body to keep the POST path stable regardless of the source identifier content.
+
+## Properties
+
+Name | Type
+------------ | -------------
+`sourceId` | string
+
+## Example
+
+```typescript
+import type { ProbeAlertmanagerSourceRequest } from ''
+
+// TODO: Update the object below with actual values
+const example = {
+  "sourceId": null,
+} satisfies ProbeAlertmanagerSourceRequest
+
+console.log(example)
+
+// Convert the instance to a JSON string
+const exampleJSON: string = JSON.stringify(example)
+console.log(exampleJSON)
+
+// Parse the JSON string back to an object
+const exampleParsed = JSON.parse(exampleJSON) as ProbeAlertmanagerSourceRequest
+console.log(exampleParsed)
+```
+
+[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

=== frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md b/frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md
index e5812e8..b41e698 100644
--- a/frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md
+++ b/frontend/src/generated/k9b-api/docs/PromoteDeterministicNextCheckRequest.md
@@ -49,5 +49,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md b/frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md
index 39a61c1..314f057 100644
--- a/frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md
+++ b/frontend/src/generated/k9b-api/docs/RecordAlertmanagerRelevanceFeedbackRequest.md
@@ -35,5 +35,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md b/frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md
index 88db45a..0ee1dc2 100644
--- a/frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md
+++ b/frontend/src/generated/k9b-api/docs/RecordNextCheckUsefulnessRequest.md
@@ -45,5 +45,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md ===
diff --git a/frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md b/frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md
index 4c99b68..07ed865 100644
--- a/frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md
+++ b/frontend/src/generated/k9b-api/docs/RunBatchNextCheckExecutionRequest.md
@@ -33,5 +33,3 @@ console.log(exampleParsed)
 ```

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-
-

=== frontend/src/generated/k9b-api/docs/RuntimeApi.md ===
diff --git a/frontend/src/generated/k9b-api/docs/RuntimeApi.md b/frontend/src/generated/k9b-api/docs/RuntimeApi.md
index c547484..2a436f9 100644
--- a/frontend/src/generated/k9b-api/docs/RuntimeApi.md
+++ b/frontend/src/generated/k9b-api/docs/RuntimeApi.md
@@ -65,4 +65,3 @@ No authorization required
 | **200** | Runtime status |  -  |

 [[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
-

=== frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts b/frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts
index 628c30f..5390708 100644
--- a/frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts
+++ b/frontend/src/generated/k9b-api/models/ApproveNextCheckRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -56,7 +56,7 @@ export function ApproveNextCheckRequestFromJSONTyped(json: any, ignoreDiscrimina
         return json;
     }
     return {
-
+
         'candidateId': json['candidateId'] == null ? undefined : json['candidateId'],
         'candidateIndex': json['candidateIndex'] == null ? undefined : json['candidateIndex'],
         'clusterLabel': json['clusterLabel'],
@@ -73,10 +73,9 @@ export function ApproveNextCheckRequestToJSONTyped(value?: ApproveNextCheckReque
     }

     return {
-
+
         'candidateId': value['candidateId'],
         'candidateIndex': value['candidateIndex'],
         'clusterLabel': value['clusterLabel'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts b/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts
index fcad5d7..df23e9a 100644
--- a/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts
+++ b/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshot200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,19 +14,19 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface CaptureIncidentSnapshot200Response
  */
 export interface CaptureIncidentSnapshot200Response {
     /**
-     *
+     *
      * @type {string}
      * @memberof CaptureIncidentSnapshot200Response
      */
     incidentId?: string;
     /**
-     *
+     *
      * @type {string}
      * @memberof CaptureIncidentSnapshot200Response
      */
@@ -49,7 +49,7 @@ export function CaptureIncidentSnapshot200ResponseFromJSONTyped(json: any, ignor
         return json;
     }
     return {
-
+
         'incidentId': json['incident_id'] == null ? undefined : json['incident_id'],
         'snapshotId': json['snapshot_id'] == null ? undefined : json['snapshot_id'],
     };
@@ -65,9 +65,8 @@ export function CaptureIncidentSnapshot200ResponseToJSONTyped(value?: CaptureInc
     }

     return {
-
+
         'incident_id': value['incidentId'],
         'snapshot_id': value['snapshotId'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts b/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts
index 6ba60ec..1fdaecc 100644
--- a/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts
+++ b/frontend/src/generated/k9b-api/models/CaptureIncidentSnapshotRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -50,7 +50,7 @@ export function CaptureIncidentSnapshotRequestFromJSONTyped(json: any, ignoreDis
         return json;
     }
     return {
-
+
         'namespace': json['namespace'],
         'sinceHours': json['sinceHours'] == null ? undefined : json['sinceHours'],
     };
@@ -66,9 +66,8 @@ export function CaptureIncidentSnapshotRequestToJSONTyped(value?: CaptureInciden
     }

     return {
-
+
         'namespace': value['namespace'],
         'sinceHours': value['sinceHours'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts b/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts
index 694fa45..a8956f3 100644
--- a/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts
+++ b/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacket200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,19 +14,19 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface CreateIncidentReviewPacket200Response
  */
 export interface CreateIncidentReviewPacket200Response {
     /**
-     *
+     *
      * @type {string}
      * @memberof CreateIncidentReviewPacket200Response
      */
     incidentId?: string;
     /**
-     *
+     *
      * @type {string}
      * @memberof CreateIncidentReviewPacket200Response
      */
@@ -49,7 +49,7 @@ export function CreateIncidentReviewPacket200ResponseFromJSONTyped(json: any, ig
         return json;
     }
     return {
-
+
         'incidentId': json['incident_id'] == null ? undefined : json['incident_id'],
         'reviewPacketId': json['review_packet_id'] == null ? undefined : json['review_packet_id'],
     };
@@ -65,9 +65,8 @@ export function CreateIncidentReviewPacket200ResponseToJSONTyped(value?: CreateI
     }

     return {
-
+
         'incident_id': value['incidentId'],
         'review_packet_id': value['reviewPacketId'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts b/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts
index cd067ee..951ed33 100644
--- a/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts
+++ b/frontend/src/generated/k9b-api/models/CreateIncidentReviewPacketRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -50,7 +50,7 @@ export function CreateIncidentReviewPacketRequestFromJSONTyped(json: any, ignore
         return json;
     }
     return {
-
+
         'bundle': json['bundle'],
         'format': json['format'] == null ? undefined : json['format'],
     };
@@ -66,9 +66,8 @@ export function CreateIncidentReviewPacketRequestToJSONTyped(value?: CreateIncid
     }

     return {
-
+
         'bundle': value['bundle'],
         'format': value['format'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts b/frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts
index 705dd97..622377b 100644
--- a/frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts
+++ b/frontend/src/generated/k9b-api/models/ExecuteNextCheckRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -62,7 +62,7 @@ export function ExecuteNextCheckRequestFromJSONTyped(json: any, ignoreDiscrimina
         return json;
     }
     return {
-
+
         'candidateId': json['candidateId'] == null ? undefined : json['candidateId'],
         'candidateIndex': json['candidateIndex'] == null ? undefined : json['candidateIndex'],
         'clusterLabel': json['clusterLabel'],
@@ -80,11 +80,10 @@ export function ExecuteNextCheckRequestToJSONTyped(value?: ExecuteNextCheckReque
     }

     return {
-
+
         'candidateId': value['candidateId'],
         'candidateIndex': value['candidateIndex'],
         'clusterLabel': value['clusterLabel'],
         'planArtifactPath': value['planArtifactPath'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts b/frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts
index 7054bc5..62f92de 100644
--- a/frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts
+++ b/frontend/src/generated/k9b-api/models/GetAuthMe200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -20,13 +20,13 @@ import { mapValues } from '../runtime';
  */
 export interface GetAuthMe200Response {
     /**
-     *
+     *
      * @type {boolean}
      * @memberof GetAuthMe200Response
      */
     authenticated?: boolean;
     /**
-     *
+     *
      * @type {string}
      * @memberof GetAuthMe200Response
      */
@@ -49,7 +49,7 @@ export function GetAuthMe200ResponseFromJSONTyped(json: any, ignoreDiscriminator
         return json;
     }
     return {
-
+
         'authenticated': json['authenticated'] == null ? undefined : json['authenticated'],
         'username': json['username'] == null ? undefined : json['username'],
     };
@@ -65,9 +65,8 @@ export function GetAuthMe200ResponseToJSONTyped(value?: GetAuthMe200Response | n
     }

     return {
-
+
         'authenticated': value['authenticated'],
         'username': value['username'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts b/frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts
index b55b2ea..94d5009 100644
--- a/frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts
+++ b/frontend/src/generated/k9b-api/models/GetAuthStatus200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -20,13 +20,13 @@ import { mapValues } from '../runtime';
  */
 export interface GetAuthStatus200Response {
     /**
-     *
+     *
      * @type {boolean}
      * @memberof GetAuthStatus200Response
      */
     authenticated?: boolean;
     /**
-     *
+     *
      * @type {string}
      * @memberof GetAuthStatus200Response
      */
@@ -49,7 +49,7 @@ export function GetAuthStatus200ResponseFromJSONTyped(json: any, ignoreDiscrimin
         return json;
     }
     return {
-
+
         'authenticated': json['authenticated'] == null ? undefined : json['authenticated'],
         'username': json['username'] == null ? undefined : json['username'],
     };
@@ -65,9 +65,8 @@ export function GetAuthStatus200ResponseToJSONTyped(value?: GetAuthStatus200Resp
     }

     return {
-
+
         'authenticated': value['authenticated'],
         'username': value['username'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/GetHealth200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/GetHealth200Response.ts b/frontend/src/generated/k9b-api/models/GetHealth200Response.ts
index 64beed9..57073f1 100644
--- a/frontend/src/generated/k9b-api/models/GetHealth200Response.ts
+++ b/frontend/src/generated/k9b-api/models/GetHealth200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,19 +14,19 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface GetHealth200Response
  */
 export interface GetHealth200Response {
     /**
-     *
+     *
      * @type {string}
      * @memberof GetHealth200Response
      */
     status?: string;
     /**
-     *
+     *
      * @type {string}
      * @memberof GetHealth200Response
      */
@@ -49,7 +49,7 @@ export function GetHealth200ResponseFromJSONTyped(json: any, ignoreDiscriminator
         return json;
     }
     return {
-
+
         'status': json['status'] == null ? undefined : json['status'],
         'timestamp': json['timestamp'] == null ? undefined : json['timestamp'],
     };
@@ -65,9 +65,8 @@ export function GetHealth200ResponseToJSONTyped(value?: GetHealth200Response | n
     }

     return {
-
+
         'status': value['status'],
         'timestamp': value['timestamp'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts b/frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts
index f14fa30..dd82b74 100644
--- a/frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts
+++ b/frontend/src/generated/k9b-api/models/GetHealthDetails200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -20,19 +20,19 @@ import { mapValues } from '../runtime';
  */
 export interface GetHealthDetails200Response {
     /**
-     *
+     *
      * @type {object}
      * @memberof GetHealthDetails200Response
      */
     checks?: object;
     /**
-     *
+     *
      * @type {string}
      * @memberof GetHealthDetails200Response
      */
     status?: string;
     /**
-     *
+     *
      * @type {string}
      * @memberof GetHealthDetails200Response
      */
@@ -55,7 +55,7 @@ export function GetHealthDetails200ResponseFromJSONTyped(json: any, ignoreDiscri
         return json;
     }
     return {
-
+
         'checks': json['checks'] == null ? undefined : json['checks'],
         'status': json['status'] == null ? undefined : json['status'],
         'timestamp': json['timestamp'] == null ? undefined : json['timestamp'],
@@ -72,10 +72,9 @@ export function GetHealthDetails200ResponseToJSONTyped(value?: GetHealthDetails2
     }

     return {
-
+
         'checks': value['checks'],
         'status': value['status'],
         'timestamp': value['timestamp'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/ListIncidents200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/ListIncidents200Response.ts b/frontend/src/generated/k9b-api/models/ListIncidents200Response.ts
index b19e262..6ae8cdf 100644
--- a/frontend/src/generated/k9b-api/models/ListIncidents200Response.ts
+++ b/frontend/src/generated/k9b-api/models/ListIncidents200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,19 +14,19 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface ListIncidents200Response
  */
 export interface ListIncidents200Response {
     /**
-     *
+     *
      * @type {Array<object>}
      * @memberof ListIncidents200Response
      */
     incidents?: Array<object>;
     /**
-     *
+     *
      * @type {number}
      * @memberof ListIncidents200Response
      */
@@ -49,7 +49,7 @@ export function ListIncidents200ResponseFromJSONTyped(json: any, ignoreDiscrimin
         return json;
     }
     return {
-
+
         'incidents': json['incidents'] == null ? undefined : json['incidents'],
         'total': json['total'] == null ? undefined : json['total'],
     };
@@ -65,9 +65,8 @@ export function ListIncidents200ResponseToJSONTyped(value?: ListIncidents200Resp
     }

     return {
-
+
         'incidents': value['incidents'],
         'total': value['total'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/ListNotifications200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/ListNotifications200Response.ts b/frontend/src/generated/k9b-api/models/ListNotifications200Response.ts
index a029197..41d90e5 100644
--- a/frontend/src/generated/k9b-api/models/ListNotifications200Response.ts
+++ b/frontend/src/generated/k9b-api/models/ListNotifications200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,19 +14,19 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface ListNotifications200Response
  */
 export interface ListNotifications200Response {
     /**
-     *
+     *
      * @type {Array<object>}
      * @memberof ListNotifications200Response
      */
     notifications?: Array<object>;
     /**
-     *
+     *
      * @type {number}
      * @memberof ListNotifications200Response
      */
@@ -49,7 +49,7 @@ export function ListNotifications200ResponseFromJSONTyped(json: any, ignoreDiscr
         return json;
     }
     return {
-
+
         'notifications': json['notifications'] == null ? undefined : json['notifications'],
         'total': json['total'] == null ? undefined : json['total'],
     };
@@ -65,9 +65,8 @@ export function ListNotifications200ResponseToJSONTyped(value?: ListNotification
     }

     return {
-
+
         'notifications': value['notifications'],
         'total': value['total'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/ListRuns200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/ListRuns200Response.ts b/frontend/src/generated/k9b-api/models/ListRuns200Response.ts
index 964fcde..4acb85c 100644
--- a/frontend/src/generated/k9b-api/models/ListRuns200Response.ts
+++ b/frontend/src/generated/k9b-api/models/ListRuns200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,19 +14,19 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface ListRuns200Response
  */
 export interface ListRuns200Response {
     /**
-     *
+     *
      * @type {Array<object>}
      * @memberof ListRuns200Response
      */
     runs?: Array<object>;
     /**
-     *
+     *
      * @type {number}
      * @memberof ListRuns200Response
      */
@@ -49,7 +49,7 @@ export function ListRuns200ResponseFromJSONTyped(json: any, ignoreDiscriminator:
         return json;
     }
     return {
-
+
         'runs': json['runs'] == null ? undefined : json['runs'],
         'total': json['total'] == null ? undefined : json['total'],
     };
@@ -65,9 +65,8 @@ export function ListRuns200ResponseToJSONTyped(value?: ListRuns200Response | nul
     }

     return {
-
+
         'runs': value['runs'],
         'total': value['total'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts b/frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts
index 02085f1..5fcabeb 100644
--- a/frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts
+++ b/frontend/src/generated/k9b-api/models/PerformAlertmanagerSourceActionRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,7 +14,7 @@

 import { mapValues } from '../runtime';
 /**
- * AlertManager source action request
+ * AlertManager source action request. sourceId is in body to support slashes in identifiers.
  * @export
  * @interface PerformAlertmanagerSourceActionRequest
  */
@@ -37,6 +37,12 @@ export interface PerformAlertmanagerSourceActionRequest {
      * @memberof PerformAlertmanagerSourceActionRequest
      */
     reason?: string;
+    /**
+     * AlertManager source identifier (may contain slashes)
+     * @type {string}
+     * @memberof PerformAlertmanagerSourceActionRequest
+     */
+    sourceId: string;
 }

 /**
@@ -45,6 +51,7 @@ export interface PerformAlertmanagerSourceActionRequest {
 export function instanceOfPerformAlertmanagerSourceActionRequest(value: object): value is PerformAlertmanagerSourceActionRequest {
     if (!('action' in value) || value['action'] === undefined) return false;
     if (!('clusterLabel' in value) || value['clusterLabel'] === undefined) return false;
+    if (!('sourceId' in value) || value['sourceId'] === undefined) return false;
     return true;
 }

@@ -57,10 +64,11 @@ export function PerformAlertmanagerSourceActionRequestFromJSONTyped(json: any, i
         return json;
     }
     return {
-
+
         'action': json['action'],
         'clusterLabel': json['clusterLabel'],
         'reason': json['reason'] == null ? undefined : json['reason'],
+        'sourceId': json['sourceId'],
     };
 }

@@ -74,10 +82,10 @@ export function PerformAlertmanagerSourceActionRequestToJSONTyped(value?: Perfor
     }

     return {
-
+
         'action': value['action'],
         'clusterLabel': value['clusterLabel'],
         'reason': value['reason'],
+        'sourceId': value['sourceId'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts ===
diff --git a/frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts b/frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts
index dff0985..c6e9cc6 100644
--- a/frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts
+++ b/frontend/src/generated/k9b-api/models/PostAuthLogin200Response.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -14,13 +14,13 @@

 import { mapValues } from '../runtime';
 /**
- *
+ *
  * @export
  * @interface PostAuthLogin200Response
  */
 export interface PostAuthLogin200Response {
     /**
-     *
+     *
      * @type {string}
      * @memberof PostAuthLogin200Response
      */
@@ -43,7 +43,7 @@ export function PostAuthLogin200ResponseFromJSONTyped(json: any, ignoreDiscrimin
         return json;
     }
     return {
-
+
         'message': json['message'] == null ? undefined : json['message'],
     };
 }
@@ -58,8 +58,7 @@ export function PostAuthLogin200ResponseToJSONTyped(value?: PostAuthLogin200Resp
     }

     return {
-
+
         'message': value['message'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts b/frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts
index 2e59096..ae90fde 100644
--- a/frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts
+++ b/frontend/src/generated/k9b-api/models/PostAuthLoginRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -20,13 +20,13 @@ import { mapValues } from '../runtime';
  */
 export interface PostAuthLoginRequest {
     /**
-     *
+     *
      * @type {string}
      * @memberof PostAuthLoginRequest
      */
     password: string;
     /**
-     *
+     *
      * @type {string}
      * @memberof PostAuthLoginRequest
      */
@@ -51,7 +51,7 @@ export function PostAuthLoginRequestFromJSONTyped(json: any, ignoreDiscriminator
         return json;
     }
     return {
-
+
         'password': json['password'],
         'username': json['username'],
     };
@@ -67,9 +67,8 @@ export function PostAuthLoginRequestToJSONTyped(value?: PostAuthLoginRequest | n
     }

     return {
-
+
         'password': value['password'],
         'username': value['username'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/ProbeAlertmanagerSourceRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/ProbeAlertmanagerSourceRequest.ts b/frontend/src/generated/k9b-api/models/ProbeAlertmanagerSourceRequest.ts
new file mode 100644
index 0000000..ef5abd9
--- /dev/null
+++ b/frontend/src/generated/k9b-api/models/ProbeAlertmanagerSourceRequest.ts
@@ -0,0 +1,65 @@
+/* tslint:disable */
+/* eslint-disable */
+/**
+ * k9b API
+ * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
+ *
+ * The version of the OpenAPI document: 0.1.0
+ *
+ *
+ * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
+ * https://openapi-generator.tech
+ * Do not edit the class manually.
+ */
+
+import { mapValues } from '../runtime';
+/**
+ * AlertManager source probe request. sourceId is in body to keep the POST path stable regardless of the source identifier content.
+ * @export
+ * @interface ProbeAlertmanagerSourceRequest
+ */
+export interface ProbeAlertmanagerSourceRequest {
+    /**
+     * AlertManager source identifier (may contain slashes)
+     * @type {string}
+     * @memberof ProbeAlertmanagerSourceRequest
+     */
+    sourceId: string;
+}
+
+/**
+ * Check if a given object implements the ProbeAlertmanagerSourceRequest interface.
+ */
+export function instanceOfProbeAlertmanagerSourceRequest(value: object): value is ProbeAlertmanagerSourceRequest {
+    if (!('sourceId' in value) || value['sourceId'] === undefined) return false;
+    return true;
+}
+
+export function ProbeAlertmanagerSourceRequestFromJSON(json: any): ProbeAlertmanagerSourceRequest {
+    return ProbeAlertmanagerSourceRequestFromJSONTyped(json, false);
+}
+
+export function ProbeAlertmanagerSourceRequestFromJSONTyped(json: any, ignoreDiscriminator: boolean): ProbeAlertmanagerSourceRequest {
+    if (json == null) {
+        return json;
+    }
+    return {
+
+        'sourceId': json['sourceId'],
+    };
+}
+
+export function ProbeAlertmanagerSourceRequestToJSON(json: any): ProbeAlertmanagerSourceRequest {
+    return ProbeAlertmanagerSourceRequestToJSONTyped(json, false);
+}
+
+export function ProbeAlertmanagerSourceRequestToJSONTyped(value?: ProbeAlertmanagerSourceRequest | null, ignoreDiscriminator: boolean = false): any {
+    if (value == null) {
+        return value;
+    }
+
+    return {
+
+        'sourceId': value['sourceId'],
+    };
+}

=== frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts b/frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts
index b29615d..b93ae29 100644
--- a/frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts
+++ b/frontend/src/generated/k9b-api/models/PromoteDeterministicNextCheckRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -99,7 +99,7 @@ export function PromoteDeterministicNextCheckRequestFromJSONTyped(json: any, ign
         return json;
     }
     return {
-
+
         'clusterLabel': json['clusterLabel'],
         'context': json['context'] == null ? undefined : json['context'],
         'description': json['description'],
@@ -123,7 +123,7 @@ export function PromoteDeterministicNextCheckRequestToJSONTyped(value?: PromoteD
     }

     return {
-
+
         'clusterLabel': value['clusterLabel'],
         'context': value['context'],
         'description': value['description'],
@@ -136,4 +136,3 @@ export function PromoteDeterministicNextCheckRequestToJSONTyped(value?: PromoteD
         'workstream': value['workstream'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts b/frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts
index 0e3edd9..78d735a 100644
--- a/frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts
+++ b/frontend/src/generated/k9b-api/models/RecordAlertmanagerRelevanceFeedbackRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -57,7 +57,7 @@ export function RecordAlertmanagerRelevanceFeedbackRequestFromJSONTyped(json: an
         return json;
     }
     return {
-
+
         'alertmanagerRelevance': json['alertmanagerRelevance'],
         'alertmanagerRelevanceSummary': json['alertmanagerRelevanceSummary'] == null ? undefined : json['alertmanagerRelevanceSummary'],
         'artifactPath': json['artifactPath'],
@@ -74,10 +74,9 @@ export function RecordAlertmanagerRelevanceFeedbackRequestToJSONTyped(value?: Re
     }

     return {
-
+
         'alertmanagerRelevance': value['alertmanagerRelevance'],
         'alertmanagerRelevanceSummary': value['alertmanagerRelevanceSummary'],
         'artifactPath': value['artifactPath'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts b/frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts
index 100c1e7..8cec1a6 100644
--- a/frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts
+++ b/frontend/src/generated/k9b-api/models/RecordNextCheckUsefulnessRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -87,7 +87,7 @@ export function RecordNextCheckUsefulnessRequestFromJSONTyped(json: any, ignoreD
         return json;
     }
     return {
-
+
         'artifactPath': json['artifactPath'],
         'judgmentScope': json['judgmentScope'] == null ? undefined : json['judgmentScope'],
         'problemClass': json['problemClass'] == null ? undefined : json['problemClass'],
@@ -109,7 +109,7 @@ export function RecordNextCheckUsefulnessRequestToJSONTyped(value?: RecordNextCh
     }

     return {
-
+
         'artifactPath': value['artifactPath'],
         'judgmentScope': value['judgmentScope'],
         'problemClass': value['problemClass'],
@@ -120,4 +120,3 @@ export function RecordNextCheckUsefulnessRequestToJSONTyped(value?: RecordNextCh
         'workstream': value['workstream'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts ===
diff --git a/frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts b/frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts
index 3d6312f..fb25974 100644
--- a/frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts
+++ b/frontend/src/generated/k9b-api/models/RunBatchNextCheckExecutionRequest.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech
@@ -50,7 +50,7 @@ export function RunBatchNextCheckExecutionRequestFromJSONTyped(json: any, ignore
         return json;
     }
     return {
-
+
         'dryRun': json['dryRun'] == null ? undefined : json['dryRun'],
         'runId': json['runId'],
     };
@@ -66,9 +66,8 @@ export function RunBatchNextCheckExecutionRequestToJSONTyped(value?: RunBatchNex
     }

     return {
-
+
         'dryRun': value['dryRun'],
         'runId': value['runId'],
     };
 }
-

=== frontend/src/generated/k9b-api/models/index.ts ===
diff --git a/frontend/src/generated/k9b-api/models/index.ts b/frontend/src/generated/k9b-api/models/index.ts
index 0767f92..4040920 100644
--- a/frontend/src/generated/k9b-api/models/index.ts
+++ b/frontend/src/generated/k9b-api/models/index.ts
@@ -16,6 +16,7 @@ export * from './ListRuns200Response';
 export * from './PerformAlertmanagerSourceActionRequest';
 export * from './PostAuthLogin200Response';
 export * from './PostAuthLoginRequest';
+export * from './ProbeAlertmanagerSourceRequest';
 export * from './PromoteDeterministicNextCheckRequest';
 export * from './RecordAlertmanagerRelevanceFeedbackRequest';
 export * from './RecordNextCheckUsefulnessRequest';

=== frontend/src/generated/k9b-api/runtime.ts ===
diff --git a/frontend/src/generated/k9b-api/runtime.ts b/frontend/src/generated/k9b-api/runtime.ts
index b23665d..f6e205e 100644
--- a/frontend/src/generated/k9b-api/runtime.ts
+++ b/frontend/src/generated/k9b-api/runtime.ts
@@ -5,7 +5,7 @@
  * Machine-readable API contract for k9b incidents, snapshots, diagnosis loop, auth, runtime status, and diagnostics endpoints.
  *
  * The version of the OpenAPI document: 0.1.0
- *
+ *
  *
  * NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).
  * https://openapi-generator.tech

=== scripts/_alertmanager_baseline_patch.py ===
diff --git a/scripts/_alertmanager_baseline_patch.py b/scripts/_alertmanager_baseline_patch.py
new file mode 100644
index 0000000..89ae222
--- /dev/null
+++ b/scripts/_alertmanager_baseline_patch.py
@@ -0,0 +1,115 @@
+#!/usr/bin/env python3
+"""Surgically patch the OpenAPI baseline with only the AlertManager-source
+changes.
+
+This avoids the unrelated baseline drift that would result from regenerating
+the entire OpenAPI schema. Only the following Alertmanager-source changes are
+applied:
+
+* ``perform_alertmanager_source_action`` path key changes from
+  ``/api/runs/{run_id}/alertmanager-sources/{source_id}/action`` to
+  ``/api/runs/{run_id}/alertmanager-sources/action`` (sourceId moves into
+  the JSON request body and the tag changes from ``incidents`` to
+  ``alertmanager``).
+* New paths are added:
+    - ``/api/runs/{run_id}/alertmanager-sources/review-packet``
+    - ``/api/runs/{run_id}/alertmanager-sources/debug-packet``
+    - ``/api/runs/{run_id}/alertmanager-sources/debug-packet/probe``
+    - ``/api/runs/{run_id}/alertmanager-sources/promotion-review``
+* The ``alertmanager`` tag description is added to the schema's top-level
+  ``tags`` array (no other tag entries are touched).
+
+All other paths and operations in the baseline are preserved exactly as they
+appear in the previous committed snapshot. Unrelated baseline drift
+(e.g. descriptions for unrelated request bodies) is intentionally NOT
+included in this ACT.
+"""
+
+from __future__ import annotations
+
+import json
+import sys
+from pathlib import Path
+
+REPO_ROOT = Path(__file__).resolve().parent.parent
+BASELINE = REPO_ROOT / "docs/api/openapi/k9b-openapi-baseline.json"
+SOURCE = REPO_ROOT / "build/openapi/k9b-openapi.json"
+
+OLD_ACTION_PATH = "/api/runs/{run_id}/alertmanager-sources/{source_id}/action"
+NEW_ACTION_PATH = "/api/runs/{run_id}/alertmanager-sources/action"
+
+NEW_PATHS: tuple[str, ...] = (
+    "/api/runs/{run_id}/alertmanager-sources/review-packet",
+    "/api/runs/{run_id}/alertmanager-sources/debug-packet",
+    "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe",
+    "/api/runs/{run_id}/alertmanager-sources/promotion-review",
+)
+
+
+def main() -> int:
+    if not BASELINE.exists():
+        print(f"baseline not found: {BASELINE}", file=sys.stderr)
+        return 1
+    if not SOURCE.exists():
+        print(f"current schema not found: {SOURCE}", file=sys.stderr)
+        return 1
+
+    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
+    current = json.loads(SOURCE.read_text(encoding="utf-8"))
+
+    paths = baseline.setdefault("paths", {})
+
+    # Move/rename perform_alertmanager_source_action from the old source_id
+    # path to the new body-based path.
+    if OLD_ACTION_PATH in paths:
+        new_action = current["paths"].get(NEW_ACTION_PATH)
+        if new_action is None:
+            print(
+                f"current schema missing {NEW_ACTION_PATH}; "
+                f"refusing to patch baseline",
+                file=sys.stderr,
+            )
+            return 1
+        paths.pop(OLD_ACTION_PATH)
+        paths[NEW_ACTION_PATH] = new_action
+
+    # Add the other four Alertmanager-source paths from the current schema.
+    for path in NEW_PATHS:
+        new_op = current["paths"].get(path)
+        if new_op is None:
+            print(
+                f"current schema missing {path}; refusing to patch baseline",
+                file=sys.stderr,
+            )
+            return 1
+        paths[path] = new_op
+
+    # Add (or update) the alertmanager tag description without touching any
+    # other tag entry.
+    tag_names = {t["name"] for t in baseline.get("tags", [])}
+    if "alertmanager" not in tag_names:
+        baseline.setdefault("tags", []).append(
+            {
+                "name": "alertmanager",
+                "description": (
+                    "AlertManager source discovery, review, debug, and action "
+                    "endpoints. All AlertManager-source operations live under "
+                    "this single tag."
+                ),
+            }
+        )
+
+    # Re-emit deterministically: sorted keys, two-space indent, trailing
+    # newline. Matches the format used by ``export_openapi_schema.py``.
+    BASELINE.write_text(
+        json.dumps(baseline, indent=2, sort_keys=True) + "\n",
+        encoding="utf-8",
+    )
+    print(f"Patched baseline at {BASELINE}")
+    print(f"  - moved {OLD_ACTION_PATH} -> {NEW_ACTION_PATH}")
+    print(f"  - added {len(NEW_PATHS)} new alertmanager-source paths")
+    return 0
+
+
+if __name__ == "__main__":
+    raise SystemExit(main())

=== scripts/generate_frontend_api_client.sh ===
diff --git a/scripts/generate_frontend_api_client.sh b/scripts/generate_frontend_api_client.sh
index 347e80e..511f63f 100755
--- a/scripts/generate_frontend_api_client.sh
+++ b/scripts/generate_frontend_api_client.sh
@@ -33,7 +33,7 @@ GENERATED_DIR="frontend/src/generated/k9b-api"
 echo "=== Generating frontend API client ==="

 # Step 1: Export OpenAPI schema
-echo "[1/3] Exporting OpenAPI schema..."
+echo "[1/4] Exporting OpenAPI schema..."
 cd "$REPO_ROOT"
 .venv/bin/python scripts/export_openapi_schema.py --output "$SCHEMA_PATH"
 if [ $? -ne 0 ]; then
@@ -43,7 +43,7 @@ fi
 echo "Schema exported to $SCHEMA_PATH"

 # Step 2: Generate TypeScript client
-echo "[2/3] Generating TypeScript client..."
+echo "[2/4] Generating TypeScript client..."

 # Check if schema exists
 if [ ! -f "$SCHEMA_PATH" ]; then
@@ -71,8 +71,12 @@ fi

 echo "Generated client written to $GENERATED_DIR"

-# Step 3: Verify generated files
-echo "[3/3] Verifying generated files..."
+# Step 3: Normalise generated output (deterministic trailing-whitespace pass)
+echo "[3/4] Normalising generated client output..."
+.venv/bin/python scripts/normalize_generated_client.py --root "$GENERATED_DIR"
+
+# Step 4: Verify generated files
+echo "[4/4] Verifying generated files..."
 if [ ! -f "$GENERATED_DIR/index.ts" ]; then
     echo "ERROR: Generated index.ts not found" >&2
     exit 3

=== scripts/normalize_generated_client.py ===
diff --git a/scripts/normalize_generated_client.py b/scripts/normalize_generated_client.py
new file mode 100644
index 0000000..76a647a
--- /dev/null
+++ b/scripts/normalize_generated_client.py
@@ -0,0 +1,102 @@
+#!/usr/bin/env python3
+"""Normalise the OpenAPI Generator TypeScript client output.
+
+The pinned ``@openapitools/openapi-generator-cli`` (v7.23.0) emits a small
+amount of trailing whitespace and sometimes a duplicated final newline in
+``.ts`` and ``.md`` files. ``git diff --check`` rejects these as whitespace
+errors, which would break ``git diff --cached --check`` for any commit that
+includes the regenerated client.
+
+This normalizer is a deterministic post-processing pass that strips trailing
+whitespace from every line and ensures the file ends with exactly one
+newline. It runs as part of ``scripts/generate_frontend_api_client.sh`` so
+the canonical generation pipeline never emits whitespace warnings.
+
+Usage:
+
+    python scripts/normalize_generated_client.py \
+        [--root frontend/src/generated/k9b-api] [--check]
+
+With ``--check``, the script exits 1 if any file would be changed and prints
+the offending paths. Without ``--check``, files are rewritten in place.
+"""
+
+from __future__ import annotations
+
+import argparse
+import sys
+from pathlib import Path
+
+# File suffixes produced by the typescript-fetch template that we accept
+# as generated outputs. We deliberately exclude binary / managed files.
+GENERATED_SUFFIXES: tuple[str, ...] = (".ts", ".md", ".json")
+
+
+def normalise(text: str) -> str:
+    """Strip trailing whitespace from every line and enforce a single
+    trailing newline.
+
+    The output is deterministic for a given input: we apply the same set of
+    transformations every run, so regeneration + normalisation produces
+    byte-stable output as long as the OpenAPI Generator template does not
+    change.
+    """
+    # Strip trailing whitespace per line.
+    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
+    # Collapse any trailing blank lines into a single newline terminator.
+    if cleaned:
+        cleaned = cleaned.rstrip("\n") + "\n"
+    else:
+        cleaned = "\n"
+    return cleaned
+
+
+def iter_generated_files(root: Path) -> list[Path]:
+    if not root.is_dir():
+        return []
+    return sorted(
+        path
+        for path in root.rglob("*")
+        if path.is_file()
+        and path.suffix in GENERATED_SUFFIXES
+        and ".openapi-generator" not in path.parts
+    )
+
+
+def main() -> int:
+    parser = argparse.ArgumentParser(description=__doc__)
+    parser.add_argument(
+        "--root",
+        type=Path,
+        default=Path("frontend/src/generated/k9b-api"),
+        help="Root directory of the generated TypeScript client "
+        "(default: frontend/src/generated/k9b-api)",
+    )
+    parser.add_argument(
+        "--check",
+        action="store_true",
+        help="Exit 1 if any file would change; do not rewrite.",
+    )
+    args = parser.parse_args()
+
+    changed: list[Path] = []
+    for path in iter_generated_files(args.root):
+        original = path.read_text(encoding="utf-8")
+        rewritten = normalise(original)
+        if original != rewritten:
+            changed.append(path)
+            if not args.check:
+                path.write_text(rewritten, encoding="utf-8")
+
+    if changed:
+        verb = "would change" if args.check else "normalised"
+        sys.stderr.write(f"{verb} {len(changed)} generated file(s):\n")
+        for path in changed:
+            sys.stderr.write(f"  {path}\n")
+        return 1 if args.check else 0
+    sys.stderr.write("no whitespace drift detected\n")
+    return 0
+
+
+if __name__ == "__main__":
+    raise SystemExit(main())

=== src/k8s_diag_agent/ui/api_contract.py ===
diff --git a/src/k8s_diag_agent/ui/api_contract.py b/src/k8s_diag_agent/ui/api_contract.py
index d2052b1..116f5c4 100644
--- a/src/k8s_diag_agent/ui/api_contract.py
+++ b/src/k8s_diag_agent/ui/api_contract.py
@@ -69,6 +69,14 @@ def build_openapi_schema() -> dict[str, Any]:
                 "description": "Read-only automatic/manual diagnosis loop endpoints.",
             },
             {"name": "runtime", "description": "Runtime status and diagnostics endpoints."},
+            {
+                "name": "alertmanager",
+                "description": (
+                    "AlertManager source discovery, review, debug, and action "
+                    "endpoints. All AlertManager-source operations live under "
+                    "this single tag."
+                ),
+            },
         ],
     }

@@ -110,14 +118,18 @@ def _build_operation_dict(op: APIOperation) -> dict[str, Any]:
             for param in op.path_params
         ]

-    # Add query params
+    # Add query params. Anything listed in `required_query_params` is emitted
+    # with `required: True`; the rest are optional. This lets the generated
+    # TypeScript client treat mandatory query parameters (e.g. AlertManager
+    # sourceId) as required positional arguments instead of optional ones.
     if op.query_params:
         params = operation.get("parameters", [])
+        required_set = set(op.required_query_params)
         for param in op.query_params:
             params.append({
                 "name": param,
                 "in": "query",
-                "required": False,
+                "required": param in required_set,
                 "schema": {"type": "string"},
             })
         operation["parameters"] = params

=== src/k8s_diag_agent/ui/api_contract_types.py ===
diff --git a/src/k8s_diag_agent/ui/api_contract_types.py b/src/k8s_diag_agent/ui/api_contract_types.py
index 6c879e9..4a8c145 100644
--- a/src/k8s_diag_agent/ui/api_contract_types.py
+++ b/src/k8s_diag_agent/ui/api_contract_types.py
@@ -47,6 +47,11 @@ class APIOperation:
     responses: tuple[APIResponse, ...] = ()
     path_params: tuple[str, ...] = ()  # Param names in path
     query_params: tuple[str, ...] = ()  # Param names in query string
+    # Subset of query_params that must be supplied. Used by OpenAPI generation to
+    # emit `required: True` so callers (including the generated TypeScript client)
+    # treat the parameter as mandatory. Defaults to empty so existing optional
+    # query params (limit/page/etc.) keep their existing semantics.
+    required_query_params: tuple[str, ...] = ()
     # Dispatch metadata - use string import paths to avoid circular imports
     handler: str = ""  # Lazy import path, e.g., "k8s_diag_agent.ui.api_openapi:handle_openapi_json"
     match: str = "exact"  # "exact" or "template"

=== src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py ===
diff --git a/src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py b/src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py
index ccc06ee..82ce742 100644
--- a/src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py
+++ b/src/k8s_diag_agent/ui/api_dispatch_adapters_nextcheck.py
@@ -1,16 +1,46 @@
 """Next-check and AlertManager dispatch adapters.

 Split from api_dispatch_adapters.py to keep file sizes below LLM-friendly thresholds.
+
+All AlertManager-source dispatch adapters parse ``sourceId`` from non-path
+locations to support opaque identifiers that contain ``/``:
+
+* ``perform_alertmanager_source_action``  -> JSON request body.
+* ``probe_alertmanager_source``            -> JSON request body.
+* ``get_alertmanager_source_debug_packet`` -> required ``sourceId`` query param.
+* ``get_alertmanager_source_promotion_review`` -> required ``sourceId`` query param.
+
+No URL-encoded path parameters are used. ``urllib.parse.unquote`` is no longer
+needed because the path itself does not carry the source identifier.
 """

 from __future__ import annotations

 from typing import TYPE_CHECKING
+from urllib.parse import parse_qs

 if TYPE_CHECKING:
     from .server import HealthUIRequestHandler


+def _query_first_value(query: str, key: str) -> str | None:
+    """Return the first decoded query value for ``key``.
+
+    ``parse_qs`` parses standard ``application/x-www-form-urlencoded`` data
+    and transparently percent-decodes values (e.g. ``%2F`` -> ``/``). No
+    additional manual ``unquote`` pass is applied afterwards, which avoids
+    double decoding while still surfacing the canonical identifier at the
+    HTTP boundary. Returns ``None`` if the key is missing or empty.
+    """
+    if not query:
+        return None
+    values = parse_qs(query, keep_blank_values=False).get(key)
+    if not values:
+        return None
+    first = values[0]
+    return first if first else None
+
+
 # Next-check adapters (POST routes)
 # =============================================================================

@@ -92,7 +122,7 @@ def handle_alertmanager_source_action_dispatch(
 ) -> None:
     """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/action.

-    Note: source_id is now read from the request body (not the URL path) to support
+    Note: sourceId is read from the request body (not the URL path) to support
     slashes in source identifiers like 'crd:monitoring/kube-prometheus-stack-alertmanager'.
     """
     from .server_alertmanager import handle_alertmanager_source_action
@@ -132,15 +162,22 @@ def handle_alertmanager_source_debug_packet_dispatch(
     query: str,
     path_params: dict[str, str],
 ) -> None:
-    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet."""
-    from urllib.parse import unquote
+    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/debug-packet.

+    The source identifier is supplied via the required ``sourceId`` query
+    parameter. The URL path does not contain ``{source_id}`` so ``unquote`` is
+    no longer required and slash-containing identifiers pass through unchanged.
+    """
     from .server_alertmanager import handle_alertmanager_source_debug_packet

     run_id = path_params.get("run_id", "")
-    source_id = path_params.get("source_id", "")
-    # Decode URL-encoded source_id
-    source_id = unquote(source_id)
+    source_id = _query_first_value(query, "sourceId")
+    if not source_id:
+        handler._send_json(
+            {"error": "sourceId query parameter is required"},
+            400,
+        )
+        return
     handle_alertmanager_source_debug_packet(handler, run_id, source_id)


@@ -149,15 +186,25 @@ def handle_alertmanager_source_debug_packet_probe_dispatch(
     query: str,
     path_params: dict[str, str],
 ) -> None:
-    """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe."""
-    from urllib.parse import unquote
+    """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/debug-packet/probe.

+    The source identifier is supplied in the JSON request body so the POST path
+    stays stable regardless of the identifier content.
+    """
     from .server_alertmanager import handle_alertmanager_source_debug_packet
+    from .server_shared import _validate_json_mutation_request

     run_id = path_params.get("run_id", "")
-    source_id = path_params.get("source_id", "")
-    # Decode URL-encoded source_id
-    source_id = unquote(source_id)
+
+    payload = _validate_json_mutation_request(handler)
+    if payload is None:
+        return
+
+    source_id = payload.get("sourceId")
+    if not isinstance(source_id, str) or not source_id:
+        handler._send_json({"error": "sourceId is required in request body"}, 400)
+        return
+
     handle_alertmanager_source_debug_packet(handler, run_id, source_id, probe_now=True)


@@ -166,13 +213,20 @@ def handle_alertmanager_source_promotion_review_dispatch(
     query: str,
     path_params: dict[str, str],
 ) -> None:
-    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review."""
-    from urllib.parse import unquote
+    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/promotion-review.

+    The source identifier is supplied via the required ``sourceId`` query
+    parameter. The URL path does not contain ``{source_id}`` so ``unquote`` is
+    no longer required and slash-containing identifiers pass through unchanged.
+    """
     from .server_alertmanager import handle_alertmanager_source_promotion_review

     run_id = path_params.get("run_id", "")
-    source_id = path_params.get("source_id", "")
-    # Decode URL-encoded source_id
-    source_id = unquote(source_id)
+    source_id = _query_first_value(query, "sourceId")
+    if not source_id:
+        handler._send_json(
+            {"error": "sourceId query parameter is required"},
+            400,
+        )
+        return
     handle_alertmanager_source_promotion_review(handler, run_id, source_id)

=== src/k8s_diag_agent/ui/api_request_schemas.py ===
diff --git a/src/k8s_diag_agent/ui/api_request_schemas.py b/src/k8s_diag_agent/ui/api_request_schemas.py
index e208987..b1e275f 100644
--- a/src/k8s_diag_agent/ui/api_request_schemas.py
+++ b/src/k8s_diag_agent/ui/api_request_schemas.py
@@ -300,3 +300,21 @@ ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA = object_schema(
     required=("sourceId", "action", "clusterLabel"),
     description="AlertManager source action request. sourceId is in body to support slashes in identifiers.",
 )
+
+
+# -----------------------------------------------------------------------------
+# AlertManager source probe
+# -----------------------------------------------------------------------------
+
+ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA = object_schema(
+    properties={
+        "sourceId": string_schema(
+            "AlertManager source identifier (may contain slashes)"
+        ),
+    },
+    required=("sourceId",),
+    description=(
+        "AlertManager source probe request. sourceId is in body to keep the "
+        "POST path stable regardless of the source identifier content."
+    ),
+)

=== src/k8s_diag_agent/ui/api_routes_nextcheck.py ===
diff --git a/src/k8s_diag_agent/ui/api_routes_nextcheck.py b/src/k8s_diag_agent/ui/api_routes_nextcheck.py
index 4685a63..36bb125 100644
--- a/src/k8s_diag_agent/ui/api_routes_nextcheck.py
+++ b/src/k8s_diag_agent/ui/api_routes_nextcheck.py
@@ -1,6 +1,18 @@
 """Next-check and AlertManager source route definitions.

 Split from api_routes_incidents.py to keep file sizes below LLM-friendly thresholds.
+
+AlertManager-source operations are owned by the ``alertmanager`` tag exclusively.
+The ``sourceId`` for these operations is transported as follows to support opaque
+identifiers that contain slashes (for example
+``crd:monitoring/alertmanager-main``):
+
+* ``perform_alertmanager_source_action``  -> sourceId in JSON request body.
+* ``probe_alertmanager_source``            -> sourceId in JSON request body.
+* ``get_alertmanager_source_debug_packet`` -> sourceId in required query string.
+* ``get_alertmanager_source_promotion_review`` -> sourceId in required query string.
+
+None of the AlertManager-source paths contain a ``{source_id}`` placeholder.
 """

 from __future__ import annotations
@@ -9,6 +21,7 @@ from .api_contract_types import APIOperation, APIResponse, APISchema
 from .api_request_schemas import (
     ALERTMANAGER_RELEVANCE_FEEDBACK_REQUEST_SCHEMA,
     ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA,
+    ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA,
     BATCH_EXECUTION_REQUEST_SCHEMA,
     DETERMINISTIC_PROMOTION_REQUEST_SCHEMA,
     NEXT_CHECK_APPROVAL_REQUEST_SCHEMA,
@@ -123,12 +136,23 @@ NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
             ),
         ),
     ),
+    # -----------------------------------------------------------------------------
+    # AlertManager sources
+    # -----------------------------------------------------------------------------
+    # Every AlertManager-source operation below carries exactly one tag:
+    # ``alertmanager``. The shared ``incidents`` tag was removed because the
+    # OpenAPI Generator splits per-tag classes; dual tags produced duplicate
+    # operations in both AlertmanagerApi and IncidentsApi.
     APIOperation(
         method="POST",
         path="/api/runs/{run_id}/alertmanager-sources/action",
         summary="Perform AlertManager source action",
-        description="Perform an action (promote/disable) on an AlertManager source. The source_id is in the request body to support slashes in source identifiers.",
-        tags=("incidents",),
+        description=(
+            "Perform an action (promote/disable) on an AlertManager source. "
+            "The sourceId is transported in the JSON request body so opaque "
+            "identifiers that contain '/' do not need URL encoding."
+        ),
+        tags=("alertmanager",),
         operation_id="perform_alertmanager_source_action",
         handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_action_dispatch",
         match="template",
@@ -142,15 +166,15 @@ NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
             ),
         ),
     ),
-    # -----------------------------------------------------------------------------
-    # AlertManager sources review packets
-    # -----------------------------------------------------------------------------
     APIOperation(
         method="GET",
         path="/api/runs/{run_id}/alertmanager-sources/review-packet",
         summary="Get AlertManager sources review packet",
-        description="Get the review packet explaining why multiple AlertManager sources were discovered.",
-        tags=("incidents", "alertmanager"),
+        description=(
+            "Get the review packet explaining why multiple AlertManager "
+            "sources were discovered."
+        ),
+        tags=("alertmanager",),
         operation_id="get_alertmanager_sources_review_packet",
         handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_sources_review_packet_dispatch",
         match="template",
@@ -165,14 +189,21 @@ NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
     ),
     APIOperation(
         method="GET",
-        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet",
+        path="/api/runs/{run_id}/alertmanager-sources/debug-packet",
         summary="Get AlertManager source debug packet",
-        description="Get a debug packet for a specific AlertManager source with probe and discovery details.",
-        tags=("incidents", "alertmanager"),
+        description=(
+            "Get a debug packet for a specific AlertManager source with "
+            "probe and discovery details. The sourceId is supplied via the "
+            "required ``sourceId`` query parameter so the URL path does "
+            "not need to be slashed-encoded."
+        ),
+        tags=("alertmanager",),
         operation_id="get_alertmanager_source_debug_packet",
         handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_debug_packet_dispatch",
         match="template",
-        path_params=("run_id", "source_id"),
+        path_params=("run_id",),
+        query_params=("sourceId",),
+        required_query_params=("sourceId",),
         responses=(
             APIResponse(
                 status_code=200,
@@ -183,14 +214,19 @@ NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
     ),
     APIOperation(
         method="POST",
-        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe",
+        path="/api/runs/{run_id}/alertmanager-sources/debug-packet/probe",
         summary="Probe AlertManager source now",
-        description="Run a live probe on the AlertManager source and return updated debug packet.",
-        tags=("incidents", "alertmanager"),
+        description=(
+            "Run a live probe on the AlertManager source and return the "
+            "updated debug packet. The sourceId is supplied in the JSON "
+            "request body."
+        ),
+        tags=("alertmanager",),
         operation_id="probe_alertmanager_source",
         handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_debug_packet_probe_dispatch",
         match="template",
-        path_params=("run_id", "source_id"),
+        path_params=("run_id",),
+        request_schema=ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA,
         responses=(
             APIResponse(
                 status_code=200,
@@ -201,14 +237,21 @@ NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
     ),
     APIOperation(
         method="GET",
-        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review",
+        path="/api/runs/{run_id}/alertmanager-sources/promotion-review",
         summary="Get AlertManager source promotion review",
-        description="Get a pre-promotion review assessing risk before promoting a source to manual.",
-        tags=("incidents", "alertmanager"),
+        description=(
+            "Get a pre-promotion review assessing risk before promoting a "
+            "source to manual. The sourceId is supplied via the required "
+            "``sourceId`` query parameter so the URL path does not need "
+            "to be slashed-encoded."
+        ),
+        tags=("alertmanager",),
         operation_id="get_alertmanager_source_promotion_review",
         handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_promotion_review_dispatch",
         match="template",
-        path_params=("run_id", "source_id"),
+        path_params=("run_id",),
+        query_params=("sourceId",),
+        required_query_params=("sourceId",),
         responses=(
             APIResponse(
                 status_code=200,

=== tests/test_openapi_alertmanager_source_contract.py ===
diff --git a/tests/test_openapi_alertmanager_source_contract.py b/tests/test_openapi_alertmanager_source_contract.py
new file mode 100644
index 0000000..56eeefc
--- /dev/null
+++ b/tests/test_openapi_alertmanager_source_contract.py
@@ -0,0 +1,405 @@
+"""OpenAPI contract tests for AlertManager-source operations.
+
+This module proves the AlertManager-source OpenAPI contract at the
+schema/registry level:
+
+* Every AlertManager-source operation exposes exactly one tag: ``alertmanager``.
+* None of the four source-specific AlertManager operations place ``sourceId``
+  in the URL path. ``sourceId`` is transported as follows:
+    - ``perform_alertmanager_source_action``: required JSON body field.
+    - ``probe_alertmanager_source``: required JSON body field.
+    - ``get_alertmanager_source_debug_packet``: required query parameter.
+    - ``get_alertmanager_source_promotion_review``: required query parameter.
+* No AlertManager-source path contains a ``{source_id}`` placeholder.
+
+Dispatcher-level assertions (the live HTTP-layer code path that the TypeScript
+client ultimately calls into) live in
+``test_openapi_alertmanager_source_dispatch.py``.
+"""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+from typing import Any
+
+from k8s_diag_agent.ui.api_contract import build_openapi_schema
+from k8s_diag_agent.ui.api_contract_types import APIOperation
+from k8s_diag_agent.ui.api_request_schemas import (
+    ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA,
+    ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA,
+)
+from k8s_diag_agent.ui.api_routes_registry import API_ROUTES
+
+# =============================================================================
+# Constants
+# =============================================================================
+
+ALERTMANAGER_SOURCE_OPERATION_IDS: tuple[str, ...] = (
+    "get_alertmanager_sources_review_packet",
+    "get_alertmanager_source_debug_packet",
+    "get_alertmanager_source_promotion_review",
+    "probe_alertmanager_source",
+    "perform_alertmanager_source_action",
+)
+
+# Source-specific operations whose URL paths must not contain {source_id}.
+SOURCE_SPECIFIC_OPERATION_IDS: tuple[str, ...] = (
+    "get_alertmanager_source_debug_packet",
+    "get_alertmanager_source_promotion_review",
+    "probe_alertmanager_source",
+    "perform_alertmanager_source_action",
+)
+
+QUERY_BASED_OPERATION_IDS: tuple[str, ...] = (
+    "get_alertmanager_source_debug_packet",
+    "get_alertmanager_source_promotion_review",
+)
+
+BODY_BASED_OPERATION_IDS: tuple[str, ...] = (
+    "perform_alertmanager_source_action",
+    "probe_alertmanager_source",
+)
+
+
+def _op_by_id(op_id: str) -> APIOperation:
+    for op in API_ROUTES:
+        if op.operation_id == op_id:
+            return op
+    raise AssertionError(f"Operation {op_id} not found in API_ROUTES registry")
+
+
+def _openapi_operation(
+    schema: dict[str, Any], op_id: str
+) -> tuple[str, str, dict[str, Any]]:
+    """Return ``(path, method, operation)`` for the operationId in the OpenAPI schema."""
+    for path, methods in schema["paths"].items():
+        for method, operation in methods.items():
+            if operation.get("operationId") == op_id:
+                return path, method, operation
+    raise AssertionError(f"OpenAPI schema missing operationId {op_id}")
+
+
+# =============================================================================
+# Schema-level tag assertions
+# =============================================================================
+
+
+class TestAlertManagerSourceTagOwnership:
+    """Every AlertManager-source operation carries exactly the alertmanager tag."""
+
+    def test_alertmanager_source_ops_have_single_alertmanager_tag(self) -> None:
+        for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
+            op = _op_by_id(op_id)
+            assert op.tags == ("alertmanager",), (
+                f"Operation {op_id} must have exactly one tag "
+                f"('alertmanager'); got {op.tags!r}"
+            )
+
+    def test_no_alertmanager_source_op_uses_legacy_dual_tag(self) -> None:
+        """The legacy dual (incidents, alertmanager) tag tuple must not appear."""
+        for op in API_ROUTES:
+            if not op.operation_id.startswith(
+                (
+                    "get_alertmanager_source",
+                    "probe_alertmanager_source",
+                    "perform_alertmanager_source_action",
+                )
+            ):
+                continue
+            assert "incidents" not in op.tags, (
+                f"Operation {op.operation_id} still carries the legacy "
+                f"'incidents' tag alongside 'alertmanager': {op.tags!r}"
+            )
+            assert op.tags == ("alertmanager",), (
+                f"Operation {op.operation_id} tags={op.tags!r} should be "
+                f"exactly ('alertmanager',)."
+            )
+
+    def test_openapi_schema_emits_single_alertmanager_tag(self) -> None:
+        schema = build_openapi_schema()
+        for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
+            _, _, operation = _openapi_operation(schema, op_id)
+            assert operation["tags"] == ["alertmanager"], (
+                f"OpenAPI operation {op_id} tags should be ['alertmanager']; "
+                f"got {operation['tags']!r}"
+            )
+
+
+# =============================================================================
+# Schema-level sourceId transport assertions
+# =============================================================================
+
+
+class TestAlertManagerSourcePathLayout:
+    """Source-specific AlertManager paths must not contain {source_id}."""
+
+    def test_source_specific_paths_have_no_source_id_placeholder(self) -> None:
+        for op_id in SOURCE_SPECIFIC_OPERATION_IDS:
+            op = _op_by_id(op_id)
+            assert "{source_id}" not in op.path, (
+                f"Operation {op_id} path {op.path!r} still contains "
+                f"the {{source_id}} placeholder."
+            )
+
+    def test_source_specific_paths_have_no_source_id_path_param(self) -> None:
+        for op_id in SOURCE_SPECIFIC_OPERATION_IDS:
+            op = _op_by_id(op_id)
+            assert "source_id" not in op.path_params, (
+                f"Operation {op_id} must not declare source_id as a path_param; "
+                f"got {op.path_params!r}"
+            )
+
+    def test_openapi_schema_paths_have_no_source_id(self) -> None:
+        schema = build_openapi_schema()
+        for op_id in SOURCE_SPECIFIC_OPERATION_IDS:
+            path, _, _ = _openapi_operation(schema, op_id)
+            assert "{source_id}" not in path, (
+                f"OpenAPI schema path {path!r} for {op_id} still contains "
+                f"{{source_id}}."
+            )
+
+
+class TestAlertManagerSourceQueryParams:
+    """Debug and promotion-review use sourceId as a required query parameter."""
+
+    def test_path_based_ops_declare_source_id_query_param(self) -> None:
+        for op_id in QUERY_BASED_OPERATION_IDS:
+            op = _op_by_id(op_id)
+            assert "sourceId" in op.query_params, (
+                f"Operation {op_id} must declare 'sourceId' as a query param."
+            )
+            assert "sourceId" in op.required_query_params, (
+                f"Operation {op_id} must declare 'sourceId' as a required "
+                f"query param."
+            )
+
+    def test_openapi_query_param_is_required_and_named_source_id(self) -> None:
+        schema = build_openapi_schema()
+        for op_id in QUERY_BASED_OPERATION_IDS:
+            _, _, operation = _openapi_operation(schema, op_id)
+            params = operation.get("parameters", [])
+            query_params = [p for p in params if p.get("in") == "query"]
+            assert any(
+                p.get("name") == "sourceId" and p.get("required") is True
+                for p in query_params
+            ), (
+                f"Operation {op_id} must declare a required query parameter "
+                f"named 'sourceId'; got {query_params!r}"
+            )
+
+    def test_path_based_ops_do_not_have_source_id_in_request_body(self) -> None:
+        schema = build_openapi_schema()
+        for op_id in QUERY_BASED_OPERATION_IDS:
+            _, _, operation = _openapi_operation(schema, op_id)
+            assert "requestBody" not in operation, (
+                f"GET operation {op_id} should not have a request body; "
+                f"got {operation.get('requestBody')!r}"
+            )
+
+
+class TestAlertManagerSourceBodyParams:
+    """Action and probe must serialise sourceId inside the JSON body."""
+
+    def test_body_based_ops_declare_source_id_request_schema(self) -> None:
+        for op_id in BODY_BASED_OPERATION_IDS:
+            op = _op_by_id(op_id)
+            assert op.request_schema is not None, (
+                f"Operation {op_id} must declare a request_schema."
+            )
+            required = op.request_schema.required or []
+            assert "sourceId" in required, (
+                f"Operation {op_id} request_schema must mark 'sourceId' as "
+                f"required; got required={required!r}"
+            )
+
+    def test_action_request_schema_requires_source_id(self) -> None:
+        schema = ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA
+        assert schema.required is not None
+        assert "sourceId" in schema.required
+
+    def test_probe_request_schema_requires_source_id(self) -> None:
+        schema = ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA
+        assert schema.required is not None
+        assert "sourceId" in schema.required
+
+    def test_body_based_ops_do_not_have_source_id_query_param(self) -> None:
+        for op_id in BODY_BASED_OPERATION_IDS:
+            op = _op_by_id(op_id)
+            assert "sourceId" not in (op.query_params or ()), (
+                f"Operation {op_id} must not declare 'sourceId' as a query "
+                f"param; got {op.query_params!r}"
+            )
+
+    def test_openapi_body_schemas_require_source_id(self) -> None:
+        schema = build_openapi_schema()
+        for op_id in BODY_BASED_OPERATION_IDS:
+            _, _, operation = _openapi_operation(schema, op_id)
+            request_body = operation.get("requestBody")
+            assert request_body is not None, (
+                f"Operation {op_id} must declare a requestBody."
+            )
+            body_schema = (
+                request_body.get("content", {})
+                .get("application/json", {})
+                .get("schema")
+            )
+            assert body_schema is not None, (
+                f"Operation {op_id} requestBody must have an application/json schema."
+            )
+            required = body_schema.get("required") or []
+            assert "sourceId" in required, (
+                f"Operation {op_id} request body must require 'sourceId'; "
+                f"got required={required!r}"
+            )
+
+
+# =============================================================================
+# Operation-IDs policy: no source_id path placeholder, single tag in JSON
+# =============================================================================
+
+
+class TestAlertManagerSourceSchemaSummary:
+    """Top-level schema invariants required by the contract."""
+
+    def test_alertmanager_tag_defined_in_schema_tags(self) -> None:
+        schema = build_openapi_schema()
+        tag_names = {t["name"] for t in schema.get("tags", [])}
+        assert "alertmanager" in tag_names
+
+    def test_alertmanager_source_ops_paths_in_paths_section(self) -> None:
+        schema = build_openapi_schema()
+        expected_paths = {
+            "/api/runs/{run_id}/alertmanager-sources/action",
+            "/api/runs/{run_id}/alertmanager-sources/review-packet",
+            "/api/runs/{run_id}/alertmanager-sources/debug-packet",
+            "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe",
+            "/api/runs/{run_id}/alertmanager-sources/promotion-review",
+        }
+        assert expected_paths.issubset(set(schema["paths"].keys())), (
+            f"Missing alertmanager-source paths: "
+            f"{expected_paths - set(schema['paths'].keys())}"
+        )
+
+
+# =============================================================================
+# Generated client invariants
+# =============================================================================
+
+
+class TestGeneratedClientOwnership:
+    """The pinned OpenAPI Generator output must put AlertManager-source
+    operations only under ``AlertmanagerApi``, never under ``IncidentsApi``."""
+
+    import_check_path = "frontend/src/generated/k9b-api"
+
+    def _generated_files(self) -> dict[str, str]:
+        """Read the generated apis/ TypeScript files from disk.
+
+        Returns a mapping from API class name (e.g. ``AlertmanagerApi``) to
+        the full contents of ``frontend/src/generated/k9b-api/apis/<name>.ts``.
+        """
+        apis_dir = Path(self.import_check_path) / "apis"
+        files: dict[str, str] = {}
+        for path in sorted(apis_dir.glob("*.ts")):
+            if path.name == "index.ts":
+                continue
+            files[path.stem] = path.read_text(encoding="utf-8")
+        return files
+
+    def _resolved_apis_dir(self) -> Path:
+        """Resolve the generated client ``apis/`` directory.
+
+        Looks for the generated client relative to the repo root. Tests can
+        run with varying CWDs; the resolver tries common candidates in order
+        before failing with a clear error.
+        """
+        candidates = [
+            Path(self.import_check_path) / "apis",
+            Path(__file__).resolve().parent.parent.parent
+            / self.import_check_path
+            / "apis",
+        ]
+        for candidate in candidates:
+            if candidate.is_dir():
+                return candidate
+        raise AssertionError(
+            f"Cannot locate generated client apis/ directory. Tried: "
+            f"{[str(c) for c in candidates]}"
+        )
+
+    @staticmethod
+    def _operation_id_to_method_name(op_id: str) -> str:
+        """Convert a snake_case operationId into the camelCase method name
+        that the OpenAPI Generator emits in TypeScript.
+
+        Example: ``get_alertmanager_source_debug_packet`` ->
+        ``getAlertmanagerSourceDebugPacket``.
+        """
+        parts = op_id.split("_")
+        return parts[0] + "".join(p.title() for p in parts[1:])
+
+    def test_each_alertmanager_source_op_appears_in_exactly_one_api_class(
+        self,
+    ) -> None:
+        """Each operationId must appear in exactly one generated API class.
+
+        This guards against the legacy dual-tag regression that produced
+        duplicate methods across ``IncidentsApi`` and ``AlertmanagerApi``.
+        """
+        apis_dir = self._resolved_apis_dir()
+        op_to_class: dict[str, str] = {}
+        for api_file in sorted(apis_dir.glob("*.ts")):
+            if api_file.name == "index.ts":
+                continue
+            content = api_file.read_text(encoding="utf-8")
+            for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
+                method_name = self._operation_id_to_method_name(op_id)
+                # The OpenAPI Generator emits a canonical method signature
+                # ``async <methodName>(`` followed by the request params.
+                if f"async {method_name}(" in content:
+                    if op_id in op_to_class:
+                        raise AssertionError(
+                            f"Operation {op_id} appears in both "
+                            f"{op_to_class[op_id]} and {api_file.stem}. "
+                            f"Each operation must live in exactly one class."
+                        )
+                    op_to_class[op_id] = api_file.stem
+        for op_id in ALERTMANAGER_SOURCE_OPERATION_IDS:
+            assert op_id in op_to_class, (
+                f"Operation {op_id} is missing from the generated client. "
+                f"Found: {sorted(op_to_class)}"
+            )
+            assert op_to_class[op_id] == "AlertmanagerApi", (
+                f"Operation {op_id} should live under AlertmanagerApi, "
+                f"got {op_to_class[op_id]!r}"
+            )
+
+    def test_no_generated_path_contains_source_id_placeholder(self) -> None:
+        """None of the four source-specific operations should keep a
+        ``{source_id}`` template in their generated path strings."""
+        apis_dir = self._resolved_apis_dir()
+        alertmanager_api = apis_dir / "AlertmanagerApi.ts"
+        assert alertmanager_api.exists(), (
+            f"Expected {alertmanager_api} to exist after generation."
+        )
+        content = alertmanager_api.read_text(encoding="utf-8")
+        assert "{source_id}" not in content, (
+            f"{alertmanager_api} still contains the {{source_id}} placeholder."
+        )
+
+
+# =============================================================================
+# Determinism: re-generating the OpenAPI schema must produce the same JSON.
+# =============================================================================
+
+
+class TestOpenAPISchemaDeterminism:
+    """Generating the schema twice must yield the same JSON text."""
+
+    def test_build_openapi_schema_is_deterministic(self) -> None:
+        schema_a = build_openapi_schema()
+        schema_b = build_openapi_schema()
+        assert json.dumps(schema_a, sort_keys=True) == json.dumps(
+            schema_b, sort_keys=True
+        )

=== tests/test_openapi_alertmanager_source_dispatch.py ===
diff --git a/tests/test_openapi_alertmanager_source_dispatch.py b/tests/test_openapi_alertmanager_source_dispatch.py
new file mode 100644
index 0000000..734e74a
--- /dev/null
+++ b/tests/test_openapi_alertmanager_source_dispatch.py
@@ -0,0 +1,273 @@
+"""Dispatcher-level tests for AlertManager-source operations.
+
+This module proves the live HTTP-layer code path that the TypeScript client
+ultimately calls into, complements the schema-level contract tests in
+``test_openapi_alertmanager_source_contract.py``.
+
+Negative slash tests prove that an opaque identifier such as
+``crd:monitoring/alertmanager-main`` can be carried end-to-end through the
+backend dispatcher without relying on URL-encoded path segments or manual
+``unquote`` round trips.
+"""
+
+from __future__ import annotations
+
+from typing import Any
+
+import pytest
+
+from k8s_diag_agent.ui.api_dispatch_adapters_nextcheck import (
+    _query_first_value,
+    handle_alertmanager_source_action_dispatch,
+    handle_alertmanager_source_debug_packet_dispatch,
+    handle_alertmanager_source_debug_packet_probe_dispatch,
+    handle_alertmanager_source_promotion_review_dispatch,
+)
+
+# A representative opaque slash-containing source identifier.
+SLASH_SOURCE_ID: str = "crd:monitoring/alertmanager-main"
+
+
+# =============================================================================
+# Slash-safe query parsing helper
+# =============================================================================
+
+
+class TestSlashSafeQueryParsing:
+    """The query helper used by the dispatchers must round-trip slashes."""
+
+    def test_query_first_value_round_trips_slash(self) -> None:
+        query = f"sourceId={SLASH_SOURCE_ID}"
+        assert _query_first_value(query, "sourceId") == SLASH_SOURCE_ID
+
+    def test_query_first_value_accepts_percent_encoded(self) -> None:
+        """Percent-encoded values are decoded by ``parse_qs`` so callers may
+        transparently transport either the canonical form (slash included) or
+        a percent-encoded form. Both decode to the same canonical identifier.
+        """
+        query = "sourceId=crd%3Amonitoring%2Falertmanager-main"
+        result = _query_first_value(query, "sourceId")
+        # parse_qs transparently decodes percent escapes; downstream sees the
+        # canonical form regardless of how the caller transported it.
+        assert result == "crd:monitoring/alertmanager-main"
+
+    def test_query_first_value_returns_none_for_missing_key(self) -> None:
+        assert _query_first_value("", "sourceId") is None
+        assert _query_first_value("foo=bar", "sourceId") is None
+
+
+# =============================================================================
+# Dispatcher stub helpers
+# =============================================================================
+
+
+class _FakeHandler:
+    """Minimal HTTP handler stand-in for dispatcher tests."""
+
+    def __init__(self) -> None:
+        self.sent: list[tuple[Any, int]] = []
+        self.status_code = 0
+
+    # Mimic BaseHTTPRequestHandler._send_json contract
+    def _send_json(self, payload: Any, code: int = 200) -> None:
+        self.sent.append((payload, code))
+        self.status_code = code
+
+
+# =============================================================================
+# Dispatcher tests: query-based sourceId
+# =============================================================================
+
+
+class TestDispatchParsesSourceIdFromQuery:
+    """The debug-packet and promotion-review dispatchers must read sourceId from query."""
+
+    def _assert_source_id_passes_to_handler(
+        self,
+        dispatcher_callable: Any,
+        monkeypatch: pytest.MonkeyPatch,
+        expected_call_args: tuple[Any, ...],
+    ) -> None:
+        captured: dict[str, Any] = {}
+
+        def fake_server_handler(handler: Any, *args: Any, **kwargs: Any) -> None:
+            captured["args"] = args
+            captured["kwargs"] = kwargs
+            captured["handler"] = handler
+
+        # The dispatcher imports its server-side handler lazily
+        # (``from .server_alertmanager import ...``). We patch the symbol on
+        # the target module so the dispatcher's import picks up the fake.
+        from k8s_diag_agent.ui import server_alertmanager
+
+        monkeypatch.setattr(
+            server_alertmanager,
+            expected_call_args[0],
+            fake_server_handler,
+            raising=False,
+        )
+        handler = _FakeHandler()
+        path_params = {"run_id": "abc12345"}
+        dispatcher_callable(handler, f"sourceId={SLASH_SOURCE_ID}", path_params)
+        assert captured["args"], "Server handler was not called"
+        # ``fake_server_handler`` declares (handler, *args, **kwargs) so
+        # ``args`` captures every positional argument *after* the handler.
+        # The handler signature is (handler, run_id, source_id), therefore
+        # ``args[0]`` is the run_id and ``args[1]`` is the source_id.
+        assert captured["args"][0] == "abc12345", captured
+        assert captured["args"][1] == SLASH_SOURCE_ID, captured
+
+    def test_debug_packet_dispatcher_reads_source_id_from_query(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        self._assert_source_id_passes_to_handler(
+            handle_alertmanager_source_debug_packet_dispatch,
+            monkeypatch,
+            ("handle_alertmanager_source_debug_packet",),
+        )
+
+    def test_promotion_review_dispatcher_reads_source_id_from_query(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        self._assert_source_id_passes_to_handler(
+            handle_alertmanager_source_promotion_review_dispatch,
+            monkeypatch,
+            ("handle_alertmanager_source_promotion_review",),
+        )
+
+    def test_missing_source_id_returns_400_for_debug_packet(self) -> None:
+        handler = _FakeHandler()
+        handle_alertmanager_source_debug_packet_dispatch(handler, "", {"run_id": "x"})
+        assert handler.sent, "Expected _send_json to be called for missing sourceId"
+        payload, code = handler.sent[0]
+        assert code == 400
+        assert "sourceId" in payload.get("error", "")
+
+    def test_missing_source_id_returns_400_for_promotion_review(self) -> None:
+        handler = _FakeHandler()
+        handle_alertmanager_source_promotion_review_dispatch(
+            handler, "other=foo", {"run_id": "x"}
+        )
+        assert handler.sent, "Expected _send_json to be called for missing sourceId"
+        payload, code = handler.sent[0]
+        assert code == 400
+        assert "sourceId" in payload.get("error", "")
+
+
+# =============================================================================
+# Dispatcher tests: body-based sourceId
+# =============================================================================
+
+
+class TestDispatchParsesSourceIdFromBody:
+    """The action and probe dispatchers must read sourceId from the JSON body."""
+
+    def test_action_dispatcher_reads_source_id_from_body(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.ui import server_alertmanager
+
+        captured: dict[str, Any] = {}
+
+        def fake_server_handler(
+            handler: Any,
+            run_id: str,
+            source_id: str,
+            payload: dict[str, Any],
+        ) -> None:
+            captured["source_id"] = source_id
+            captured["run_id"] = run_id
+            captured["payload"] = payload
+
+        monkeypatch.setattr(
+            server_alertmanager,
+            "handle_alertmanager_source_action",
+            fake_server_handler,
+            raising=False,
+        )
+        # The action dispatcher relies on _validate_json_mutation_request to
+        # parse the request body. Patch it on server_shared so the dispatcher
+        # sees the body we want it to read.
+        from k8s_diag_agent.ui import server_shared
+
+        def fake_validate(handler: Any) -> dict[str, Any] | None:
+            return {
+                "sourceId": SLASH_SOURCE_ID,
+                "action": "promote",
+                "clusterLabel": "c1",
+            }
+
+        monkeypatch.setattr(
+            server_shared,
+            "_validate_json_mutation_request",
+            fake_validate,
+            raising=False,
+        )
+        handler = _FakeHandler()
+        handle_alertmanager_source_action_dispatch(handler, "", {"run_id": "run1"})
+        assert captured.get("source_id") == SLASH_SOURCE_ID, captured
+        assert captured.get("run_id") == "run1", captured
+
+    def test_probe_dispatcher_reads_source_id_from_body(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.ui import server_alertmanager
+
+        captured: dict[str, Any] = {}
+
+        def fake_server_handler(
+            handler: Any,
+            run_id: str,
+            source_id: str,
+            *,
+            probe_now: bool = False,
+        ) -> None:
+            captured["source_id"] = source_id
+            captured["run_id"] = run_id
+            captured["probe_now"] = probe_now
+
+        monkeypatch.setattr(
+            server_alertmanager,
+            "handle_alertmanager_source_debug_packet",
+            fake_server_handler,
+            raising=False,
+        )
+        from k8s_diag_agent.ui import server_shared
+
+        def fake_validate(handler: Any) -> dict[str, Any] | None:
+            return {"sourceId": SLASH_SOURCE_ID}
+
+        monkeypatch.setattr(
+            server_shared,
+            "_validate_json_mutation_request",
+            fake_validate,
+            raising=False,
+        )
+        handler = _FakeHandler()
+        handle_alertmanager_source_debug_packet_probe_dispatch(
+            handler, "", {"run_id": "run2"}
+        )
+        assert captured.get("source_id") == SLASH_SOURCE_ID, captured
+        assert captured.get("run_id") == "run2", captured
+        assert captured.get("probe_now") is True, captured
+
+    def test_action_dispatcher_rejects_missing_source_id(
+        self, monkeypatch: pytest.MonkeyPatch
+    ) -> None:
+        from k8s_diag_agent.ui import server_shared
+
+        def fake_validate(handler: Any) -> dict[str, Any] | None:
+            return {"action": "promote", "clusterLabel": "c1"}
+
+        monkeypatch.setattr(
+            server_shared,
+            "_validate_json_mutation_request",
+            fake_validate,
+            raising=False,
+        )
+        handler = _FakeHandler()
+        handle_alertmanager_source_action_dispatch(handler, "", {"run_id": "x"})
+        assert handler.sent, "Expected 400 for missing sourceId"
+        payload, code = handler.sent[0]
+        assert code == 400
+        assert "sourceId" in payload.get("error", "")

## Workflow anchors
