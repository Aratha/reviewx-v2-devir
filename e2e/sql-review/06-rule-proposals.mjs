import {withBrowser, accounts, signIn, apiStatus} from '../shared/harness.mjs';
import {openAdminSection, openLibrary} from './navigation.mjs';

const STAMP = Date.now();
const RULE_SUMMARY = `E2E öneri özeti ${STAMP}.`;
const RULE_TEXT = `E2E öneri ayrıntısı ${STAMP}: geçici tablolar işlem sonunda DROP edilmelidir.`;
const REJECTED_SUMMARY = `E2E reddedilecek öneri ${STAMP}.`;
const REJECTION = `E2E ret gerekçesi ${STAMP}`;
const GROUP_NAME = `E2E öneri grubu ${STAMP}`;

async function proposeRule(page, summary, text) {
  const form = page.getByRole('form', {name: 'Yeni kural önerisi'});
  await form.getByLabel('Özet (tek cümle, zorunlu)').fill(summary);
  await form.getByLabel('Ayrıntılı kural metni (zorunlu)').fill(text);
  await form.getByRole('button', {name: 'Öneriyi gönder'}).click();
  await page.getByRole('region', {name: 'Önerilerim'}).getByText(summary).waitFor();
}

/**
 * rule-proposals Acceptance 4 (local): a reviewer, without any permission (Decision 6), proposes a rule with its summary and detailed text, and a group holding
 * that rule once it is published; the super admin reads the detailed text and approves both, so
 * the rule and the group appear in new versions; a rejected proposal shows its reason to the
 * reviewer. The scenario removes its rule and group from the draft and publishes again in
 * `finally`.
 */
await withBrowser('rule proposals: everyone proposes, approval and rejection', async ({page, assert, newPage}) => {
  const admin = page;
  await signIn(admin, accounts.superAdmin);
  const reviewer = await newPage();
  await signIn(reviewer, accounts.reviewer);
  let changed = false;
  try {
    const previous = (await apiStatus(admin, '/rule-set/versions/latest')).body.number;
    // Super admin: there is no permission list any more.
    await openAdminSection(admin, 'Kural onayları');
    assert.equal(await admin.getByRole('tab', {name: 'Öneri yetkisi'}).count(), 0);

    // Reviewer: the rule library offers proposals at once; a rule needs the summary and the text.
    await openLibrary(reviewer, 'Kural önerilerim');
    const form = reviewer.getByRole('form', {name: 'Yeni kural önerisi'});
    await form.getByLabel('Ayrıntılı kural metni (zorunlu)').fill(RULE_TEXT);
    assert.equal(await form.getByRole('button', {name: 'Öneriyi gönder'}).isDisabled(), true);
    await proposeRule(reviewer, RULE_SUMMARY, RULE_TEXT);
    await reviewer.getByRole('tab', {name: 'Kural öner'}).click();
    await proposeRule(reviewer, REJECTED_SUMMARY, `E2E reddedilecek ayrıntı ${STAMP}.`);

    // Super admin: the detailed text is visible; approve one, reject the other with a reason.
    await admin.reload();
    await admin.getByRole('tab', {name: /^Kural önerileri/}).click();
    const card = admin.getByRole('listitem', {name: RULE_SUMMARY});
    await card.getByText(RULE_TEXT).waitFor();
    await card.getByRole('button', {name: `${RULE_SUMMARY} onayla`}).click();
    await card.waitFor({state: 'detached'});
    changed = true;
    const rejected = admin.getByRole('listitem', {name: REJECTED_SUMMARY});
    await rejected.getByRole('button', {name: `${REJECTED_SUMMARY} reddet`}).click();
    await rejected.getByLabel(/Ret gerekçesi/).fill(REJECTION);
    await rejected.getByRole('button', {name: 'Reddi gönder'}).click();
    await rejected.waitFor({state: 'detached'});

    const afterRule = (await apiStatus(reviewer, '/rule-set/versions/latest')).body;
    assert.equal(afterRule.number, previous + 1);
    const newRule = [...afterRule.critical, ...afterRule.normal].find((rule) => rule.text === RULE_TEXT);
    assert.ok(newRule, 'the approved rule is published');
    assert.equal(newRule.summary, RULE_SUMMARY);

    // Reviewer: decisions and the reason are visible; propose a group holding the new rule.
    await reviewer.reload();
    await reviewer.getByRole('tab', {name: 'Önerilerim'}).click();
    const history = reviewer.getByRole('region', {name: 'Önerilerim'});
    await history.getByText(`Ret gerekçesi: ${REJECTION}`).waitFor();
    await history.getByText(new RegExp(`sürüm ${previous + 1} · ${newRule.id}`)).waitFor();
    await reviewer.getByRole('tab', {name: 'Grup öner'}).click();
    const groupForm = reviewer.getByRole('form', {name: 'Yeni grup önerisi'});
    await groupForm.getByLabel('Grup adı (zorunlu)').fill(GROUP_NAME);
    await groupForm.getByLabel('Kural ara').fill(newRule.id);
    await groupForm.getByRole('checkbox', {name: new RegExp(`^${newRule.id}\\b`)}).check();
    await groupForm.getByRole('button', {name: 'Öneriyi gönder'}).click();
    await reviewer.getByRole('region', {name: 'Önerilerim'}).getByText(GROUP_NAME).waitFor();

    // Super admin approves the group; it is published with the rule as its member.
    await admin.reload();
    await admin.getByRole('tab', {name: /^Grup önerileri/}).click();
    const groupCard = admin.getByRole('listitem', {name: GROUP_NAME});
    await groupCard.getByText(RULE_SUMMARY).waitFor();
    await groupCard.getByRole('button', {name: `${GROUP_NAME} onayla`}).click();
    await groupCard.waitFor({state: 'detached'});
    const afterGroup = (await apiStatus(reviewer, '/rule-set/versions/latest')).body;
    assert.equal(afterGroup.number, previous + 2);
    const group = afterGroup.groups.find((item) => item.name === GROUP_NAME);
    assert.ok(group, 'the approved group is published');
    const member = [...afterGroup.critical, ...afterGroup.normal].find((rule) => rule.id === newRule.id);
    assert.deepEqual(member.rule_group_ids, [group.id]);
  } finally {
    if (changed) {
      const current = await apiStatus(admin, '/rule-set');
      const keep = (rule) => rule.text !== RULE_TEXT;
      const groups = current.body.groups.filter((item) => item.name !== GROUP_NAME);
      const known = new Set(groups.map((item) => item.id));
      const clean = (rule) => ({...rule, rule_group_ids: rule.rule_group_ids.filter((id) => known.has(id))});
      const saved = await apiStatus(admin, '/rule-set/draft', {
        method: 'PUT',
        body: {
          base_revision: current.body.revision,
          critical: current.body.critical.filter(keep).map(clean),
          normal: current.body.normal.filter(keep).map(clean),
          groups,
        },
      });
      assert.equal(saved.status, 200);
      const republished = await apiStatus(admin, '/rule-set/versions', {
        method: 'POST',
        body: {base_revision: saved.body.revision},
      });
      assert.ok([200, 201].includes(republished.status));
    }
  }
});
