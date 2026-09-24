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
{{- $repository := required (printf "%s.image.repository zorunludur" $component) $image.repository -}}
{{- $digest := default "" $image.digest -}}
{{- if $digest -}}
{{- if not (regexMatch "^sha256:[0-9a-f]{64}$" $digest) -}}
{{- fail (printf "%s.image.digest küçük harfli bir sha256 digest olmalıdır" $component) -}}
{{- end -}}
{{- printf "%s@%s" $repository $digest -}}
{{- else -}}
{{- $tag := required (printf "%s.image.tag digest boşken zorunludur" $component) $image.tag -}}
{{- if not (regexMatch "^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$" $tag) -}}
{{- fail (printf "%s.image.tag geçerli bir OCI etiketi olmalıdır" $component) -}}
{{- end -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end }}

{{/* Hareketli latest etiketi her Pod başlangıcında yeniden çekilir; SHA/digest önbellekten. */}}
{{- define "dwhcodereview.imagePullPolicy" -}}
{{- if and (not .digest) (eq (toString .tag) "latest") -}}
Always
{{- else -}}
IfNotPresent
{{- end -}}
{{- end }}

{{/* Eski chart'taki PVC kimliği korunur; yükseltmede /app/data verisi taşınmaz, yerinde kalır. */}}
{{- define "dwhcodereview.dataClaimName" -}}
{{- $fullname := printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- $fullname = .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- printf "%s-data" (printf "%s-backend" $fullname | trunc 63 | trimSuffix "-") -}}
{{- end }}

{{/* backend/config.py env değerleri; CORS_ORIGINS boşsa Ingress host'undan türetilir. */}}
{{- define "dwhcodereview.backendConfig" -}}
{{- $config := deepCopy .Values.backend.config -}}
{{- if not (get $config "CORS_ORIGINS") -}}
{{- $_ := set $config "CORS_ORIGINS" (printf "https://%s" .Values.frontend.ingress.host) -}}
{{- end -}}
{{- toYaml $config -}}
{{- end }}

{{/*
İmajdaki default.conf docker-compose için 80'i dinler ve /api'yi "backend" adına
iletir. Kümede Nginx non-root 8080'de yalnız SPA sunar; /api Ingress'ten backend'e gider.
*/}}
{{- define "dwhcodereview.frontendNginxConfig" -}}
server {
  listen 8080;
  server_name _;
  root /usr/share/nginx/html;
  index index.html;
  location / {
    try_files $uri $uri/ /index.html;
  }
}
{{- end }}

{{/* İmajın root varsayan ana yapılandırması (user, pid) yerine; yazılabilir yollar emptyDir. */}}
{{- define "dwhcodereview.frontendNginxMainConfig" -}}
worker_processes auto;
error_log /dev/stderr notice;
pid /var/run/nginx.pid;
events {
  worker_connections 1024;
}
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                  '$status $body_bytes_sent "$http_referer" '
                  '"$http_user_agent" "$http_x_forwarded_for"';
  access_log /dev/stdout main;
  sendfile on;
  keepalive_timeout 65;
  include /etc/nginx/conf.d/*.conf;
}
{{- end }}
