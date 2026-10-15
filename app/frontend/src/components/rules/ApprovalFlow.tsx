import {Card} from '@/components/ui/Card';

export type ApprovalFlowRole = 'manager' | 'proposer' | 'decider';

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
  manager: {
    title: 'Taslak nasıl yayımlanır?',
    steps: [
      {title: 'Taslağı düzenleyin', where: 'Kurallar', text: 'Kural ekleyin, tek cümlelik özet yazın, gruplara atayın.'},
      {
        title: 'Onaya gönderin',
        where: 'Kurallar → Onaya gönder',
        text: 'Değişiklikler kaydedilir ve yayın isteği süper yöneticiye düşer.',
      },
      {
        title: 'Süper yönetici inceler',
        where: 'Kural onayları → Yayın istekleri',
        text: 'Yayımlanmış sürüme göre eklenen, değişen ve silinen kuralları görür.',
      },
      {
        title: 'Karar',
        where: 'Bu sayfanın üstü',
        text: 'Onaylanınca yeni sürüm hemen yayımlanır; reddedilirse gerekçe burada görünür.',
      },
    ],
  },
  proposer: {
    title: 'Öneriniz nasıl yayımlanır?',
    steps: [
      {
        title: 'Öneriyi yazın',
        where: 'Kural önerilerim → Kural öner / Grup öner',
        text: 'Kural için tek cümlelik özet ve ayrıntılı metin zorunludur.',
      },
      {
        title: 'Onaya düşer',
        where: 'Süper yönetici → Kural onayları',
        text: 'Öneri "Bekliyor" durumunda süper yöneticinin onay listesine girer.',
      },
      {
        title: 'Karar',
        where: 'Kural önerilerim → Önerilerim',
        text: 'Onaylanırsa yeni sürümde herkesin kullanımına açılır; reddedilirse gerekçe görünür.',
      },
    ],
  },
  decider: {
    title: 'Onay akışı',
    steps: [
      {
        title: 'Gelen işler',
        where: 'Bu sayfa',
        text: 'Yetkili kullanıcıların kural ve grup önerileri ile kural yöneticilerinin yayın istekleri buraya düşer.',
      },
      {
        title: 'İnceleyin',
        where: 'Sekmeler',
        text: 'Ayrıntılı kural metnini ve yayın isteğinin farkını görün.',
      },
      {
        title: 'Onaylayın veya reddedin',
        where: 'Her kartın altı',
        text: 'Onay hemen yeni sürüm yayımlar; ret gerekçesi isteyene görünür.',
      },
      {
        title: 'Yetki verin',
        where: 'Öneri yetkisi',
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
