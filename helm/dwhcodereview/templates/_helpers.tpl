{{/* Chart name */}}
{{- define "dwhcodereview.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified app name */}}
{{- define "dwhcodereview.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Chart label */}}
{{- define "dwhcodereview.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels */}}
{{- define "dwhcodereview.labels" -}}
helm.sh/chart: {{ include "dwhcodereview.chart" . }}
app.kubernetes.io/name: {{ include "dwhcodereview.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels for the backend component */}}
{{- define "dwhcodereview.backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "dwhcodereview.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: backend
{{- end -}}

{{/* Selector labels for the frontend component */}}
{{- define "dwhcodereview.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "dwhcodereview.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end -}}

{{/* Component resource names */}}
{{- define "dwhcodereview.backend.fullname" -}}
{{- printf "%s-backend" (include "dwhcodereview.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "dwhcodereview.frontend.fullname" -}}
{{- printf "%s-frontend" (include "dwhcodereview.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Full image references */}}
{{- define "dwhcodereview.backend.image" -}}
{{- $img := .Values.backend.image -}}
{{- printf "%s/%s:%s" $img.registry $img.repository ($img.tag | default .Chart.AppVersion) -}}
{{- end -}}

{{- define "dwhcodereview.frontend.image" -}}
{{- $img := .Values.frontend.image -}}
{{- printf "%s/%s:%s" $img.registry $img.repository ($img.tag | default .Chart.AppVersion) -}}
{{- end -}}

{{/* Name of the Secret holding backend .env values */}}
{{- define "dwhcodereview.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-config" (include "dwhcodereview.fullname" .) -}}
{{- end -}}
{{- end -}}
