{{/* Proje uzantısı: hiçbir workload üretilmeden önce kapalı-başarısız kontrol. */}}
{{- define "dwhcodereview.validate" -}}
{{- range $component := list "backend" "frontend" -}}
{{- $repository := required (printf "%s.image.repository zorunludur" $component) (index $.Values $component).image.repository -}}
{{- $registry := index (splitList "/" $repository) 0 -}}
{{- if has $registry (list "ghcr.io" "docker.io" "index.docker.io" "quay.io" "gcr.io" "registry.k8s.io" "public.ecr.aws") -}}
{{- fail (printf "%s.image.repository iç registry yolunu kullanmalıdır; %s node üzerinde çözülemez" $component $registry) -}}
{{- end -}}
{{- end -}}
{{- range $component := list "backend" "frontend" -}}
{{- range $direction := list "ingress" "egress" -}}
{{- $peerKey := ternary "from" "to" (eq $direction "ingress") -}}
{{- $invalidRule := printf "%s.networkPolicy.%s kuralları boş olmayan hedef ve port içermelidir" $component $direction -}}
{{- range $rule := index (index $.Values $component).networkPolicy $direction -}}
{{- if not (kindIs "map" $rule) -}}{{- fail $invalidRule -}}{{- end -}}
{{- if or (empty (index $rule $peerKey)) (empty $rule.ports) -}}{{- fail $invalidRule -}}{{- end -}}
{{- range $peer := index $rule $peerKey -}}
{{- if not (kindIs "map" $peer) -}}{{- fail "boş ağ hedefi yasaktır" -}}{{- end -}}
{{- if empty $peer -}}{{- fail "boş ağ hedefi yasaktır" -}}{{- end -}}
{{- range $selectorKey := list "namespaceSelector" "podSelector" -}}
{{- if hasKey $peer $selectorKey -}}
{{- $selector := index $peer $selectorKey -}}
{{- if not (kindIs "map" $selector) -}}{{- fail (printf "boş %s yasaktır" $selectorKey) -}}{{- end -}}
{{- if empty $selector.matchLabels -}}{{- fail (printf "boş %s yasaktır" $selectorKey) -}}{{- end -}}
{{- end -}}
{{- end -}}
{{- if hasKey $peer "ipBlock" -}}
{{- $block := index $peer "ipBlock" -}}
{{- if not (kindIs "map" $block) -}}{{- fail "boş ipBlock yasaktır" -}}{{- end -}}
{{- if has (toString $block.cidr) (list "0.0.0.0/0" "::/0") -}}
{{- fail "sınırsız ağ CIDR'i (0.0.0.0/0, ::/0) yasaktır" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- range $key := list "MSSQL_CONNECTION_STRING" "MSSQL_PASSWORD" "API_ACCESS_TOKEN" "API_ADMIN_TOKEN" "LLM_API_KEY" -}}
{{- if hasKey $.Values.backend.config $key -}}
{{- fail (printf "backend.config sır içeremez (%s); değeri backend.existingSecret Secret'ına yazın" $key) -}}
{{- end -}}
{{- end -}}
{{- $ingress := .Values.frontend.ingress -}}
{{- if eq (toString $ingress.tlsSecretName) "ailab-tls" -}}
{{- if not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?\\.ailab(-test)?\\.kuveytturk\\.com\\.tr$" (toString $ingress.host)) -}}
{{- fail (printf "frontend.ingress.host %s, ailab-tls wildcard sertifikasının (*.ailab-test.kuveytturk.com.tr, *.ailab.kuveytturk.com.tr) kapsamında değildir" (toString $ingress.host)) -}}
{{- end -}}
{{- end -}}
{{- $persistence := .Values.backend.persistence -}}
{{- if $persistence.enabled -}}
{{- if and (has $persistence.accessMode (list "ReadWriteOnce" "ReadWriteOncePod")) (gt (int .Values.backend.replicaCount) 1) -}}
{{- fail (printf "backend.persistence.accessMode %s iken backend.replicaCount 1 olmalıdır" $persistence.accessMode) -}}
{{- end -}}
{{- end -}}
{{- end -}}
