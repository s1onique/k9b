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
