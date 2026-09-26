import {useState, type FormEvent} from 'react';
import {Alert} from '@/components/ui/Alert';
import {Button} from '@/components/ui/Button';
import {Card} from '@/components/ui/Card';
import {Field} from '@/components/ui/Field';
import {PageHeader} from '@/components/ui/PageHeader';
import {ErrorState, LoadingState} from '@/components/ui/States';
import {useResource} from '@/hooks/useResource';
import {MANAGED_BY_DEPLOYMENT, RUNTIME_ONLY} from '@/lib/connectionText';
import {describeError} from '@/lib/errorMessages';
import {ConnectionService} from '@/services/connections';
import type {LlmChatApi, LlmConnectionUpdate, LlmConnectionView} from '@/types/sqlReview';

const CHAT_API_LABELS: Record<LlmChatApi, string> = {
  openai: 'OpenAI uyumlu (messages, …/chat/completions)',
  api_v1_chat: 'POST /api/v1/chat (system_prompt + input, ör. LM Studio)',
};

/**
 * LLM connection settings (sql-review llm-connection Requirement 13): format, base address,
 * optional chat address, model and key in `local`; read-only format and model elsewhere.
 */
export default function LlmConnectionPage() {
  const view = useResource('llm-connection', (signal) => ConnectionService.llm(signal));
  const [saved, setSaved] = useState(false);
  return (
    <div className="page">
      <PageHeader
        title="LLM bağlantısı"
        description="İncelemeler yalnız kurum içi ağdaki onaylı LLM ucuna gider; adres bu ağın dışındaysa kayıt reddedilir."
      />
      {view.status === 'error' && <ErrorState message={describeError(view.error)} onRetry={view.reload} />}
      {view.status === 'loading' && view.data === undefined && <LoadingState label="Ayarlar yükleniyor…" />}
      {view.data && !view.data.editable && (
        <Card title="Bağlantı durumu">
          <div className="stack">
            <Alert tone="info">{MANAGED_BY_DEPLOYMENT}</Alert>
            <dl className="facts">
              <div>
                <dt>Ortam</dt>
                <dd>{view.data.environment}</dd>
              </div>
              <div>
                <dt>İstek biçimi</dt>
                <dd>{CHAT_API_LABELS[view.data.chat_api]}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd className="mono">{view.data.model || '—'}</dd>
              </div>
            </dl>
          </div>
        </Card>
      )}
      {view.data && view.data.editable && (
        <LlmConnectionForm
          key={JSON.stringify(view.data)}
          view={view.data}
          saved={saved}
          onSaved={(next) => {
            setSaved(true);
            view.replace(next);
          }}
          onReload={() => {
            setSaved(false);
            view.reload();
          }}
        />
      )}
    </div>
  );
}

function LlmConnectionForm({
  view,
  saved,
  onSaved,
  onReload,
}: {
  view: LlmConnectionView;
  saved: boolean;
  onSaved: (view: LlmConnectionView) => void;
  onReload: () => void;
}) {
  const [chatApi, setChatApi] = useState<LlmChatApi>(view.chat_api);
  const [baseUrl, setBaseUrl] = useState(view.base_url ?? '');
  const [chatUrl, setChatUrl] = useState(view.chat_url ?? '');
  const [model, setModel] = useState(view.model);
  const [apiKey, setApiKey] = useState('');
  const [removeKey, setRemoveKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const update: LlmConnectionUpdate = {
      chat_api: chatApi,
      base_url: baseUrl.trim(),
      chat_url: chatUrl.trim(),
      model: model.trim(),
    };
    // No key field keeps the stored key; an empty string removes it.
    if (removeKey) update.api_key = '';
    else if (apiKey !== '') update.api_key = apiKey;
    try {
      const next = await ConnectionService.saveLlm(update);
      setApiKey('');
      setRemoveKey(false);
      onSaved(next);
    } catch (reason) {
      setError(describeError(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Bağlantı ayarları">
      <form className="form-grid" onSubmit={(event) => void save(event)} noValidate>
        <Alert tone="info">{RUNTIME_ONLY}</Alert>
        {saved && error === null && <Alert tone="success">LLM bağlantı ayarları kaydedildi.</Alert>}
        {error && <Alert tone="error">{error}</Alert>}
        <Field id="llm-chat-api" label="İstek biçimi">
          <select
            id="llm-chat-api"
            className="select"
            value={chatApi}
            onChange={(event) => setChatApi(event.target.value as LlmChatApi)}
          >
            <option value="openai">{CHAT_API_LABELS.openai}</option>
            <option value="api_v1_chat">{CHAT_API_LABELS.api_v1_chat}</option>
          </select>
        </Field>
        <Field
          id="llm-base-url"
          label="Temel adres"
          hint={
            chatApi === 'openai'
              ? 'Sonu /v1 ile biten adres; istek …/v1/chat/completions adresine gider.'
              : 'Sunucu kökü veya …/v1; istek /api/v1/chat adresine gider.'
          }
        >
          <input
            id="llm-base-url"
            className="input"
            type="url"
            value={baseUrl}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="llm-base-url-hint"
            onChange={(event) => setBaseUrl(event.target.value)}
          />
        </Field>
        <Field id="llm-chat-url" label="Sohbet adresi (isteğe bağlı)" hint="Boş bırakılırsa temel adresten üretilir.">
          <input
            id="llm-chat-url"
            className="input"
            type="url"
            value={chatUrl}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="llm-chat-url-hint"
            onChange={(event) => setChatUrl(event.target.value)}
          />
        </Field>
        {view.resolved_chat_url && (
          <p className="subtle">
            Kullanılan adres: <span className="mono">{view.resolved_chat_url}</span>
          </p>
        )}
        <Field id="llm-model" label="Model">
          <input
            id="llm-model"
            className="input"
            value={model}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setModel(event.target.value)}
          />
        </Field>
        <Field
          id="llm-api-key"
          label="API anahtarı"
          hint={view.api_key_set ? 'Kayıtlı anahtar var. Boş bırakırsanız korunur.' : 'Kayıtlı anahtar yok; isteğe bağlıdır.'}
        >
          <input
            id="llm-api-key"
            className="input"
            type="password"
            value={apiKey}
            autoComplete="new-password"
            disabled={removeKey}
            aria-describedby="llm-api-key-hint"
            onChange={(event) => setApiKey(event.target.value)}
          />
        </Field>
        {view.api_key_set && (
          <label className="check">
            <input
              type="checkbox"
              checked={removeKey}
              onChange={(event) => {
                setRemoveKey(event.target.checked);
                if (event.target.checked) setApiKey('');
              }}
            />
            <span>Kayıtlı anahtarı kaldır</span>
          </label>
        )}
        <div className="row">
          <Button type="submit" variant="primary" disabled={busy} busy={busy}>
            Kaydet
          </Button>
          <Button variant="ghost" onClick={onReload} disabled={busy}>
            Yenile
          </Button>
        </div>
      </form>
    </Card>
  );
}
