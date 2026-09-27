import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import catalogue0 from "@/locales/tr.json";

type MessageTree = { [key: string]: string | MessageTree };
type MessageValues = Record<string, string | number>;

/** One catalogue per configured locale, in `.kt-scaffold/answers.yml` order. */
const catalogues: Record<string, MessageTree> = {
  "tr": catalogue0,
};
const primaryLocale = "tr";
const supportedLocales: readonly string[] = Object.keys(catalogues);

function lookup(catalogue: MessageTree, key: string): string | undefined {
  const direct = catalogue[key];
  if (typeof direct === "string") return direct;
  let current: string | MessageTree | undefined = catalogue;
  for (const part of key.split(".")) {
    if (typeof current === "string" || current === undefined) return undefined;
    const entry: [string, string | MessageTree] | undefined = Object.entries(current).find(
      ([candidate]) => candidate === part,
    );
    if (entry === undefined) return undefined;
    current = entry[1];
  }
  return typeof current === "string" ? current : undefined;
}

function interpolate(message: string, values: MessageValues | undefined): string {
  if (values === undefined) return message;
  return message.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    Object.hasOwn(values, name) ? String(values[name]) : placeholder,
  );
}

interface IntlValue {
  locale: string;
  locales: readonly string[];
  setLocale: (value: string) => void;
  t: (key: string, values?: MessageValues) => string;
}

const Context = createContext<IntlValue | null>(null);

export function IntlProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState(primaryLocale);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const value = useMemo(
    () => ({
      locale,
      locales: supportedLocales,
      setLocale: (next: string) => {
        if (supportedLocales.includes(next)) setLocale(next);
      },
      t: (key: string, values?: MessageValues) =>
        interpolate(
          lookup(catalogues[locale] ?? catalogues[primaryLocale], key) ??
            lookup(catalogues[primaryLocale], key) ??
            key,
          values,
        ),
    }),
    [locale],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useIntl(): IntlValue {
  const value = useContext(Context);
  if (!value) throw new Error("useIntl must be used inside IntlProvider");
  return value;
}
