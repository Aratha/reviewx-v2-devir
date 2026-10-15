import {useId, useMemo, useState, type KeyboardEvent} from 'react';
import {useNavigate} from 'react-router';
import {Dialog} from '@/components/ui/Dialog';
import {Icon, type IconName} from '@/components/ui/Icon';
import {useAppNavigation} from '@/contexts/NavigationContext';

interface Command {
  to: string;
  label: string;
  group: string;
  icon: IconName;
  keywords: string;
}

const REVIEW_LABELS: Record<string, string> = {
  '/inceleme': 'Nesne incelemesi',
  '/sql-inceleme': 'SQL betiği incelemesi',
  '/zamanlanmis-incelemeler': 'Zamanlanmış incelemeler',
};

/** Turkish-aware, accent-tolerant folding for matching typed text. */
function fold(value: string): string {
  return value
    .toLocaleLowerCase('tr-TR')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ı/g, 'i');
}

/**
 * Ctrl+K quick navigation: every destination the user may open, filtered as they type, chosen
 * with the arrow keys and Enter. It only navigates; each page still checks access itself.
 */
export function CommandPalette({onClose}: {onClose: () => void}) {
  const navigation = useAppNavigation();
  const navigate = useNavigate();
  const listId = useId();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  const commands = useMemo<Command[]>(() => {
    const seen = new Set<string>();
    const all: Command[] = [
      {to: '/', label: 'Ana sayfa', group: 'Git', icon: 'home', keywords: 'genel baslangic'},
      ...(navigation.primary.some((item) => item.to === '/inceleme')
        ? [
            ...navigation.reviewModes.map((mode) => ({
              to: mode.to,
              label: REVIEW_LABELS[mode.to] ?? mode.label,
              group: 'İnceleme',
              icon: mode.icon,
              keywords: 'incele review kontrol',
            })),
            {to: '/gecmis', label: 'İnceleme geçmişi', group: 'İnceleme', icon: 'history' as const, keywords: 'gecmis rapor csv'},
            ...navigation.libraryModes.map((mode) => ({
              to: mode.to,
              label: mode.label,
              group: 'Kural kitaplığı',
              icon: mode.icon,
              keywords: 'kural oneri',
            })),
          ]
        : []),
      ...navigation.adminSections.map((section) => ({
        to: `/yonetim/${section.id}`,
        label: section.label,
        group: 'Yönetim',
        icon: section.icon,
        keywords: `yonetim ayar ${section.summary}`,
      })),
    ];
    return all.filter((command) => !seen.has(command.to) && seen.add(command.to));
  }, [navigation]);

  const needle = fold(query.trim());
  const shown = needle
    ? commands.filter((command) => fold(`${command.label} ${command.group} ${command.keywords}`).includes(needle))
    : commands;
  const current = Math.min(active, Math.max(shown.length - 1, 0));

  function go(command: Command | undefined) {
    if (!command) return;
    onClose();
    navigate(command.to);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((current + step + shown.length) % Math.max(shown.length, 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      go(shown[current]);
    }
  }

  return (
    <Dialog title="Hızlı geçiş" onClose={onClose} size="sm">
      <div className="cmdk">
        <input
          className="input cmdk-input"
          role="combobox"
          aria-label="Gidilecek sayfa"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={shown.length > 0 ? `${listId}-${current}` : undefined}
          aria-autocomplete="list"
          placeholder="Sayfa ya da ayar arayın…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
        />
        <ul id={listId} role="listbox" aria-label="Sonuçlar" className="cmdk-list">
          {shown.map((command, index) => (
            <li
              key={command.to}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === current}
              className="cmdk-option"
              onMouseEnter={() => setActive(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                go(command);
              }}
            >
              <span className="stat-icon">
                <Icon name={command.icon} />
              </span>
              <span className="grow truncate">{command.label}</span>
              <span className="subtle cmdk-group">{command.group}</span>
            </li>
          ))}
          {shown.length === 0 && <li className="subtle cmdk-empty">Eşleşen sayfa yok.</li>}
        </ul>
        <p className="subtle cmdk-hint">
          <kbd>↑</kbd> <kbd>↓</kbd> ile seçin, <kbd>Enter</kbd> ile açın, <kbd>Esc</kbd> ile kapatın.
        </p>
      </div>
    </Dialog>
  );
}
