import {Card} from '@/components/ui/Card';

export type ApprovalFlowRole = 'proposer' | 'decider';

interface Step {
  title: string;
  where: string;
  text: string;
}

/**
 * How a rule change reaches a published version (sql-review rule-proposals Requirement 6, 7): the
 * steps, the screen each step happens on and who acts. Every published change passes the super
 * admin; only the super admin publishes directly.
 */
const STEPS: Record<ApprovalFlowRole, {title: string; steps: Step[]}> = {
  proposer: {
    title: 'Öneriniz nasıl yayımlanır?',
    steps: [
      {
        title: 'Öneriyi yazın',
        where: 'Kural kitaplığı → Kural önerilerim',
        text: 'Kural için tek cümlelik özet ve ayrıntılı metin zorunludur.',
      },
      {
        title: 'Onaya düşer',
        where: 'Süper yönetici: Yönetim → Kural onayları',
        text: 'Öneri "Bekliyor" durumunda süper yöneticinin onay listesine girer.',
      },
      {
        title: 'Karar',
        where: 'Kural kitaplığı → Kural önerilerim',
        text: 'Onaylanırsa yeni sürümde herkesin kullanımına açılır; reddedilirse gerekçe görünür.',
      },
    ],
  },
  decider: {
    title: 'Onay akışı',
    steps: [
      {
        title: 'Gelen işler',
        where: 'Yönetim → Kural onayları',
        text: 'Kullanıcıların kural ve grup önerileri buraya düşer.',
      },
      {
        title: 'İnceleyin',
        where: 'Sekmeler',
        text: 'Ayrıntılı kural metnini ve gerekçeyi görün.',
      },
      {
        title: 'Onaylayın veya reddedin',
        where: 'Her kartın altı',
        text: 'Onay hemen yeni sürüm yayımlar; ret gerekçesi isteyene görünür.',
      },
      {
        title: 'Yetki verin',
        where: 'Kural onayları → Öneri yetkisi',
        text: 'Kimlerin kural ve grup önerebileceğini belirleyin.',
      },
    ],
  },
};

export function ApprovalFlow({role}: {role: ApprovalFlowRole}) {
  const flow = STEPS[role];
  return (
    <Card title={flow.title} labelledBy={`approval-flow-${role}`}>
      <ol className="flow-steps">
        {flow.steps.map((step) => (
          <li key={step.title} className="flow-step">
            <strong>{step.title}</strong>
            <span className="flow-where">{step.where}</span>
            <span>{step.text}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
