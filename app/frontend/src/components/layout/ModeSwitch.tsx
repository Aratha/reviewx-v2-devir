import {Link, useLocation} from 'react-router';
import {Icon, type IconName} from '@/components/ui/Icon';

export interface ModeItem {
  to: string;
  label: string;
  icon: IconName;
  /** A live review of this kind is running. */
  busy?: boolean;
}

/**
 * A segmented switch between sibling pages that share one place in the main menu, such as the
 * three ways to review. Each segment is a link, so the address, Back and a new tab keep working.
 */
export function ModeSwitch({label, items}: {label: string; items: ModeItem[]}) {
  const {pathname} = useLocation();
  if (items.length < 2) return null;
  return (
    <nav className="segmented" aria-label={label}>
      {items.map((item) => (
        <Link key={item.to} to={item.to} aria-current={pathname === item.to ? 'page' : undefined}>
          <Icon name={item.icon} />
          <span>{item.label}</span>
          {item.busy && <span className="pulse-dot" role="img" aria-label="İnceleme sürüyor" />}
        </Link>
      ))}
    </nav>
  );
}
