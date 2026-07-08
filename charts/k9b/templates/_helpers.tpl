{{/*
k9b helper templates.
Provides common label and name generation functions.
*/}}

{{/*
Expand the name of the chart release.
*/}}
{{- define "k9b.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "k9b.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create the backend deployment name.
*/}}
{{- define "k9b.backend.fullname" -}}
{{- printf "%s-backend" (include "k9b.fullname" .) }}
{{- end }}

{{/*
Create the scheduler deployment name.
*/}}
{{- define "k9b.scheduler.fullname" -}}
{{- printf "%s-scheduler" (include "k9b.fullname" .) }}
{{- end }}

{{/*
Create the frontend deployment name.
*/}}
{{- define "k9b.frontend.fullname" -}}
{{- printf "%s-frontend" (include "k9b.fullname" .) }}
{{- end }}

{{/*
Create the service account name.
*/}}
{{- define "k9b.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- .Values.serviceAccount.name | default (printf "%s-sa" (include "k9b.fullname" .)) }}
{{- else }}
{{- .Values.serviceAccount.name | default "default" }}
{{- end }}
{{- end }}

{{/*
Create the health config ConfigMap name.
*/}}
{{- define "k9b.healthConfig.fullname" -}}
{{- printf "%s-health-config" (include "k9b.fullname" .) }}
{{- end }}

{{/*
Create the runs PVC name.
*/}}
{{- define "k9b.runs.fullname" -}}
{{- printf "%s-runs" (include "k9b.fullname" .) }}
{{- end }}

{{/*
Create chart labels.
*/}}
{{- define "k9b.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "k9b.selectorLabels" . }}
{{- if .Chart.Version }}
app.kubernetes.io/version: {{ .Chart.Version | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels for all k9b resources (shared base).
Used in Ingress and other cross-component resources.
*/}}
{{- define "k9b.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k9b.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Selector labels for backend component only.
Used in backend Deployment spec.selector and backend Service.
*/}}
{{- define "k9b.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k9b.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Selector labels for scheduler component only.
Used in scheduler Deployment spec.selector.
*/}}
{{- define "k9b.scheduler.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k9b.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: scheduler
{{- end }}

{{/*
Selector labels for frontend component only.
Used in frontend Deployment spec.selector and frontend Service.
*/}}
{{- define "k9b.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "k9b.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Common labels for backend component (includes component label).
*/}}
{{- define "k9b.backend.labels" -}}
{{ include "k9b.backend.selectorLabels" . }}
{{- end }}

{{/*
Common labels for scheduler component (includes component label).
*/}}
{{- define "k9b.scheduler.labels" -}}
{{ include "k9b.scheduler.selectorLabels" . }}
{{- end }}

{{/*
Common labels for frontend component (includes component label).
*/}}
{{- define "k9b.frontend.labels" -}}
{{ include "k9b.frontend.selectorLabels" . }}
{{- end }}

{{/*
Resolve the admin auth secret name.

Priority:
1. backend.auth.existingSecret (if non-empty)
2. Chart-managed secret name (if backend.auth.adminPasswordHash is set)
3. Fail with a clear error if neither is set and auth is enabled.
*/}}
{{- define "k9b.adminAuthSecretName" -}}
{{- $existingSecret := .Values.backend.auth.existingSecret | default "" }}
{{- $adminPasswordHash := .Values.backend.auth.adminPasswordHash | default "" }}
{{- if .Values.backend.auth.enabled }}
  {{- if and (ne $existingSecret "") }}
    {{- $existingSecret }}
  {{- else if ne $adminPasswordHash "" }}
    {{- printf "%s-admin-auth" (include "k9b.fullname" .) }}
  {{- else }}
    {{- $failMsg := "backend.auth.enabled=true but neither backend.auth.existingSecret nor backend.auth.adminPasswordHash is set. " }}
    {{- $failMsg = printf "%sEither provide an existingSecret name or set adminPasswordHash for local/dev use." $failMsg }}
    {{- fail $failMsg }}
  {{- end }}
{{- else }}
  {{- /* Auth not enabled, return empty to skip secretKeyRef entirely */ }}
  {{- "" }}
{{- end }}
{{- end }}

{{/*
Determine if chart should create the admin auth secret.
Returns true only when auth is enabled, existingSecret is empty, and adminPasswordHash is set.
*/}}
{{- define "k9b.createAdminAuthSecret" -}}
{{- if and .Values.backend.auth.enabled (not .Values.backend.auth.existingSecret) .Values.backend.auth.adminPasswordHash }}
true
{{- else }}
false
{{- end }}
{{- end }}

{{/*
Determine RBAC cluster scope mode.

Priority:
1. rbac.clusterScoped if explicitly set (true/false)
2. rbac.clusterWide if explicitly set (true/false) - DEPRECATED alias
3. Default to true (cluster-wide)

Returns "true" for cluster-scoped or "false" for namespace-scoped.
*/}}
{{- define "k9b.rbac.clusterScoped" -}}
{{- if hasKey .Values.rbac "clusterScoped" }}
{{- .Values.rbac.clusterScoped | toString }}
{{- else if hasKey .Values.rbac "clusterWide" }}
{{- .Values.rbac.clusterWide | toString }}
{{- else }}
{{- "true" }}
{{- end }}
{{- end }}

{{/*
Resolve internal API secret name for backend and scheduler.

When sqlite/backend-api mode is enabled, both backend and scheduler must reference
the same Secret (or Secrets with identical token values).

Policy:
- Returns the backend internalApi.existingSecret if set
- Falls back to scheduler internalApi.existingSecret if backend is empty
- Returns empty string if neither is configured (validation will catch this)
*/}}
{{- define "k9b.internalApiSecretName" -}}
{{- $backendSecret := .Values.backend.internalApi.existingSecret | default "" }}
{{- $schedulerSecret := .Values.scheduler.incidentPromotion.internalApi.existingSecret | default "" }}
{{- if and (eq .Values.backend.incidentStore.backend "sqlite") (or (eq .Values.scheduler.incidentPromotion.mode "backend-api") (eq .Values.scheduler.incidentPromotion.mode "auto")) }}
  {{- /* sqlite + backend-api/auto mode: need secrets */ }}
  {{- if $backendSecret }}
    {{- $backendSecret }}
  {{- else if $schedulerSecret }}
    {{- $schedulerSecret }}
  {{- else }}
    {{- "" }}
  {{- end }}
{{- else if eq .Values.scheduler.incidentPromotion.mode "backend-api" }}
  {{- /* backend-api mode only */ }}
  {{- if $schedulerSecret }}
    {{- $schedulerSecret }}
  {{- else }}
    {{- "" }}
  {{- end }}
{{- else }}
  {{- /* local mode: no secret required */ }}
  {{- "" }}
{{- end }}
{{- end }}

{{/*
Validate incident promotion configuration.

This template MUST be called when sqlite or backend-api mode is enabled.
It fails Helm rendering if configuration is incomplete.

Fails with clear message if:
- backend.incidentStore.backend=sqlite but backend.internalApi.existingSecret is empty
- scheduler.incidentPromotion.mode=backend-api but scheduler.internalApi.existingSecret is empty
- scheduler.incidentPromotion.mode=auto but scheduler.internalApi.existingSecret is empty
  (auto resolves to backend-api when process_role=scheduler)
- scheduler.incidentPromotion.mode=backend-api but scheduler.internalApi.backendUrl is empty
*/}}
{{- define "k9b.validateIncidentPromotionConfig" }}
{{- /* SQLite mode requires backend internal API token */ }}
{{- if eq .Values.backend.incidentStore.backend "sqlite" }}
  {{- if not .Values.backend.internalApi.existingSecret }}
    {{- fail "backend.incidentStore.backend=sqlite requires backend.internalApi.existingSecret to be set. Create a secret: kubectl create secret generic k9b-internal-api --from-literal=K9B_INTERNAL_API_TOKEN=<your-token>" }}
  {{- end }}
{{- end }}

{{- /* backend-api or auto mode requires scheduler internal API token */ }}
{{- if or (eq .Values.scheduler.incidentPromotion.mode "backend-api") (eq .Values.scheduler.incidentPromotion.mode "auto") }}
  {{- /* Backend URL must be configured for backend-api/auto mode */ }}
  {{- if not .Values.scheduler.incidentPromotion.internalApi.backendUrl }}
    {{- fail "scheduler.incidentPromotion.mode=backend-api requires scheduler.incidentPromotion.internalApi.backendUrl to be set" }}
  {{- end }}

  {{- /* auto mode ALWAYS requires scheduler token because scheduler process_role=scheduler
       causes dispatcher to resolve auto to backend-api at runtime */ }}
  {{- if eq .Values.scheduler.incidentPromotion.mode "auto" }}
    {{- if not .Values.scheduler.incidentPromotion.internalApi.existingSecret }}
      {{- fail "scheduler.incidentPromotion.mode=auto requires scheduler.incidentPromotion.internalApi.existingSecret to be set. The scheduler process_role=scheduler causes dispatcher to resolve auto to backend-api, which requires internal API token. Create a secret: kubectl create secret generic k9b-internal-api --from-literal=K9B_INTERNAL_API_TOKEN=<your-token>" }}
    {{- end }}
  {{- end }}

  {{- /* backend-api mode: require secrets based on backend type */ }}
  {{- if eq .Values.scheduler.incidentPromotion.mode "backend-api" }}
    {{- /* When backend is sqlite, both backend AND scheduler need secrets */ }}
    {{- if eq .Values.backend.incidentStore.backend "sqlite" }}
      {{- if not .Values.backend.internalApi.existingSecret }}
        {{- fail "sqlite backend with backend-api scheduler requires backend.internalApi.existingSecret to be set" }}
      {{- end }}
      {{- if not .Values.scheduler.incidentPromotion.internalApi.existingSecret }}
        {{- fail "sqlite backend with backend-api scheduler requires scheduler.incidentPromotion.internalApi.existingSecret to be set. Both backend and scheduler must reference a Secret containing K9B_INTERNAL_API_TOKEN" }}
      {{- end }}
    {{- else }}
      {{- /* Non-sqlite backend with backend-api mode: only scheduler needs secret */ }}
      {{- if not .Values.scheduler.incidentPromotion.internalApi.existingSecret }}
        {{- fail "scheduler.incidentPromotion.mode=backend-api requires scheduler.incidentPromotion.internalApi.existingSecret to be set. Create a secret: kubectl create secret generic k9b-internal-api --from-literal=K9B_INTERNAL_API_TOKEN=<your-token>" }}
      {{- end }}
    {{- end }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Check if internal API token is required for backend.

Returns true if backend.incidentStore.backend=sqlite (backend needs to validate tokens).
*/}}
{{- define "k9b.backendRequiresInternalApiToken" -}}
{{- if eq .Values.backend.incidentStore.backend "sqlite" }}
true
{{- else }}
false
{{- end }}
{{- end }}

{{/*
Check if internal API token is required for scheduler.

Returns true if scheduler.incidentPromotion.mode is backend-api or auto.
*/}}
{{- define "k9b.schedulerRequiresInternalApiToken" -}}
{{- if or (eq .Values.scheduler.incidentPromotion.mode "backend-api") (eq .Values.scheduler.incidentPromotion.mode "auto") }}
true
{{- else }}
false
{{- end }}
{{- end }}
