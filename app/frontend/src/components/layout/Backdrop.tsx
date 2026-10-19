import {useEffect, useRef} from 'react';

/** Made-up T-SQL that reads like warehouse code; it never comes from a review. */
const CODE = [
  'CREATE PROCEDURE dbo.usp_LoadCustomer',
  'AS',
  'BEGIN',
  '  SET NOCOUNT ON;',
  '  SELECT c.CustomerId, c.Segment, s.Balance',
  '  FROM dbo.Customer c WITH (NOLOCK)',
  '  LEFT JOIN stg.Balance s ON s.CustomerId = c.CustomerId',
  '  INNER JOIN dm.Branch b ON b.BranchId = s.BranchId',
  '  WHERE c.Status = 1',
  '    AND s.AsOfDate >= DATEADD(DAY, -1, GETDATE());',
  '',
  '  SELECT * INTO #tmp FROM dbo.Ledger;',
  '  UPDATE t SET t.Amount = t.Amount * r.Rate',
  '  FROM #tmp t JOIN ref.FxRate r ON r.Ccy = t.Ccy;',
  '',
  '  DECLARE cur CURSOR FOR SELECT Id FROM #tmp;',
  '  MERGE dm.FactBalance AS tgt',
  '  USING #tmp AS src ON tgt.Id = src.Id',
  '  WHEN MATCHED THEN UPDATE SET tgt.Amount = src.Amount',
  '  WHEN NOT MATCHED THEN INSERT (Id, Amount)',
  '    VALUES (src.Id, src.Amount);',
  '  DROP TABLE #tmp;',
  'END',
  '',
  'CREATE VIEW dm.vw_ActiveAccount AS',
  '  SELECT a.AccountNo, a.OpenDate, a.CloseDate',
  '  FROM edw.Account a',
  '  WHERE a.IsActive = 1 AND a.ValidTo IS NULL;',
  '',
  'SELECT TOP 10 Id, Name FROM dbo.Orders ORDER BY Id;',
];

/** Colours come from the design tokens (rules/32); the canvas reads them once. */
const TOKENS = {
  text: '--color-code-text',
  scan: '--color-scan',
  pass: '--color-success',
  flag: '--color-danger',
  flagSoft: '--color-danger-soft',
};

interface Line {
  text: string;
  /** When the scan last passed over the line (ms), and what it found. */
  seen: number;
  flagged: boolean;
}

/** Height of one code line in CSS pixels. */
const LINE = 22;
/** The scan crosses the screen in this many milliseconds, then rests. */
const SWEEP = 7000;
const REST = 2500;
/** How long a verdict stays beside a line. */
const VERDICT = 5200;

/**
 * The ReviewX backdrop: faint SQL drifts up behind the pages while a review scan sweeps down the
 * screen, line by line. Each line it passes lights up and earns a verdict in the gutter: a check
 * for most, a highlighted cross for some, the way a review marks findings. Purely decorative and
 * hidden from assistive technology; a still frame for users who prefer less motion; it pauses
 * while the tab is hidden.
 */
export function Backdrop() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext('2d');
    if (!element || !context) return;
    const style = getComputedStyle(document.documentElement);
    const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
    const colour = {
      text: read(TOKENS.text, 'rgba(168, 177, 218, 0.14)'),
      scan: read(TOKENS.scan, 'rgba(124, 244, 255, 0.5)'),
      pass: read(TOKENS.pass, '#3dfcb4'),
      flag: read(TOKENS.flag, '#ff6b93'),
      flagSoft: read(TOKENS.flagSoft, 'rgba(255, 93, 143, 0.13)'),
    };
    const mono = read('--font-mono', 'monospace');
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

    let width = 0;
    let height = 0;
    let columns: Line[][] = [];
    let columnWidth = 0;
    let offset = 0;
    let frame = 0;
    let last = 0;
    let clock = 0;

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      element!.width = width * ratio;
      element!.height = height * ratio;
      context!.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = Math.max(1, Math.min(3, Math.floor(width / 520)));
      columnWidth = width / count;
      const rows = Math.ceil(height / LINE) + 2;
      columns = Array.from({length: count}, (_, column) =>
        Array.from({length: rows}, (_, row) => ({
          text: CODE[(row + column * 11) % CODE.length],
          seen: -Infinity,
          flagged: false,
        })),
      );
    }

    function draw() {
      context!.clearRect(0, 0, width, height);
      context!.font = `13px ${mono}`;
      context!.textBaseline = 'middle';
      const cycle = clock % (SWEEP + REST);
      const scanY = still ? height * 0.42 : (cycle / SWEEP) * (height + 120) - 60;
      const scanning = still || cycle < SWEEP;

      columns.forEach((lines, column) => {
        const left = column * columnWidth + 56;
        lines.forEach((line, row) => {
          const y = row * LINE - offset + LINE / 2;
          if (y < -LINE || y > height + LINE) return;
          // The scan reaches the line: decide its verdict once per pass.
          if (scanning && Math.abs(y - scanY) < LINE / 2 && clock - line.seen > SWEEP) {
            line.seen = clock;
            line.flagged = line.text.trim().length > 14 && Math.random() < 0.14;
          }
          const age = clock - line.seen;
          const near = scanning ? Math.max(0, 1 - Math.abs(y - scanY) / 90) : 0;
          const verdict = line.text.trim() !== '' && age < VERDICT ? 1 - age / VERDICT : 0;

          if (line.flagged && verdict > 0) {
            context!.globalAlpha = verdict;
            context!.fillStyle = colour.flagSoft;
            context!.fillRect(left - 30, y - LINE / 2 + 2, columnWidth - 60, LINE - 4);
          }
          context!.globalAlpha = 1;
          context!.fillStyle = colour.text;
          context!.fillText(line.text, left, y);
          if (near > 0) {
            context!.globalAlpha = near * 0.55;
            context!.fillStyle = colour.scan;
            context!.fillText(line.text, left, y);
          }
          if (verdict > 0) {
            context!.globalAlpha = verdict * (line.flagged ? 0.95 : 0.5);
            context!.fillStyle = line.flagged ? colour.flag : colour.pass;
            context!.fillText(line.flagged ? '✕' : '✓', left - 24, y);
          }
        });
      });

      if (scanning) {
        const beam = context!.createLinearGradient(0, scanY - 70, 0, scanY + 4);
        beam.addColorStop(0, 'transparent');
        beam.addColorStop(1, colour.scan);
        context!.globalAlpha = 0.16;
        context!.fillStyle = beam;
        context!.fillRect(0, scanY - 70, width, 74);
        context!.globalAlpha = 0.55;
        context!.fillRect(0, scanY + 3, width, 1);
      }
      context!.globalAlpha = 1;
    }

    function loop(time: number) {
      const elapsed = last ? Math.min(time - last, 64) : 16;
      last = time;
      clock += elapsed;
      offset = (offset + elapsed * 0.006) % LINE;
      if (offset < elapsed * 0.006) {
        // A line left the top: move every column up by one row.
        for (const lines of columns) lines.push(lines.shift()!);
      }
      draw();
      frame = window.requestAnimationFrame(loop);
    }

    function start() {
      window.cancelAnimationFrame(frame);
      last = 0;
      if (still) draw();
      else if (!document.hidden) frame = window.requestAnimationFrame(loop);
    }

    function onResize() {
      resize();
      start();
    }

    resize();
    start();
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', start);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', start);
    };
  }, []);

  return <canvas ref={canvas} className="backdrop" aria-hidden="true" />;
}
