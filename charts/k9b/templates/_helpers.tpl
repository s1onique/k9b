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
{{- $existingSecret := .Values.backend.auth.existingSecret | default "" -}}
{{- $adminPasswordHash := .Values.backend.auth.adminPasswordHash | default "" -}}
{{- if .Values.backend.auth.enabled -}}
  {{- if and (ne $existingSecret "") -}}
    {{- $existingSecret -}}
  {{- else if ne $adminPasswordHash "" -}}
    {{- printf "%s-admin-auth" (include "k9b.fullname" .) -}}
  {{- else -}}
    {{- $failMsg := "backend.auth.enabled=true but neither backend.auth.existingSecret nor backend.auth.adminPasswordHash is set. " -}}
    {{- $failMsg = printf "%sEither provide an existingSecret name or set adminPasswordHash for local/dev use." $failMsg -}}
    {{- fail $failMsg -}}
  {{- end -}}
{{- else -}}
  {{- /* Auth not enabled, return empty to skip secretKeyRef entirely */ -}}
  {{- "" -}}
{{- end -}}
{{- end -}}

{{/*
Determine if chart should create the admin auth secret.
Returns true only when auth is enabled, existingSecret is empty, and adminPasswordHash is set.
*/}}
{{- define "k9b.createAdminAuthSecret" -}}
{{- if and .Values.backend.auth.enabled (not .Values.backend.auth.existingSecret) .Values.backend.auth.adminPasswordHash -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}
