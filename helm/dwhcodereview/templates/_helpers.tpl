{{- define "generated.resourceName" -}}
{{- $root := index . 0 -}}
{{- $component := index . 1 -}}
{{- $release := $root.Release.Name | trunc 18 | trimSuffix "-" -}}
{{- $slug := $root.Chart.Name | trunc 18 | trimSuffix "-" -}}
{{- $identity := printf "%s/%s/%s/%s" $root.Release.Namespace $root.Release.Name $root.Chart.Name $component -}}
{{- printf "%s-%s-%s-%s" $release $slug $component (sha256sum $identity | trunc 12) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "generated.workloadLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name | quote }}
app.kubernetes.io/part-of: {{ .root.Chart.Name | quote }}
app.kubernetes.io/instance: {{ .root.Release.Name | quote }}
app.kubernetes.io/component: {{ .component | quote }}
scaffold.kt.internal/workload: {{ include "generated.resourceName" (list .root .component) | quote }}
{{- end }}

{{- define "generated.annotations" -}}
scaffold.kt.internal/product-name: {{ index .Chart.Annotations "scaffold.kt.internal/product-name" | quote }}
scaffold.kt.internal/product-slug: {{ .Chart.Name | quote }}
scaffold.kt.internal/release-namespace: {{ .Release.Namespace | quote }}
{{- end }}

{{- define "generated.image" -}}
{{- $component := index . 0 -}}
{{- $image := index . 1 -}}
{{- $repository := required (printf "%s.image.repository is required" $component) $image.repository -}}
{{- $digest := default "" $image.digest -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail (printf "%s.image.digest must be a lowercase sha256 digest" $component) -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- $tag := required (printf "%s.image.tag is required when digest is empty" $component) $image.tag -}}
{{- if not (regexMatch "^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$" $tag) -}}
{{- fail (printf "%s.image.tag must be a valid OCI tag" $component) -}}
{{- end -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end }}
