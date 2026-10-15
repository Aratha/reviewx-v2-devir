import {message} from '../shared/harness.mjs';

/** The main menu in the top bar. */
export function mainMenu(page) {
  return page.getByRole('navigation', {name: message('shell.navigation')});
}

/**
 * Open a section of the single Yönetim page (Kurallar, Kural onayları, SQL bağlantısı, ...): the
 * main menu's "Yönetim", then the section in the rail; the section title is a second-level heading.
 */
export async function openAdminSection(page, section, heading = section) {
  await mainMenu(page).getByRole('link', {name: /^Yönetim/}).click();
  const rail = page.getByRole('navigation', {name: 'Yönetim bölümleri'});
  await rail.getByRole('link', {name: new RegExp(`^${section}`)}).click();
  await page.getByRole('heading', {name: heading, level: 2}).waitFor();
}

/** Open one way to review under "İnceleme": Nesneler, SQL betiği or Zamanlanmış. */
export async function openReview(page, mode, heading) {
  await mainMenu(page).getByRole('link', {name: 'İnceleme', exact: true}).click();
  await page.getByRole('navigation', {name: 'İnceleme türü'}).getByRole('link', {name: mode}).click();
  if (heading) await page.getByRole('heading', {name: heading, level: 1}).waitFor();
}

/**
 * Open a page of the rule library: Yayımlanmış kurallar (where the menu item lands) or Kural
 * önerilerim, which the switch offers only to a user allowed to propose.
 */
export async function openLibrary(page, item) {
  await mainMenu(page).getByRole('link', {name: 'Kural kitaplığı'}).click();
  if (item !== 'Yayımlanmış kurallar')
    await page.getByRole('navigation', {name: 'Kural kitaplığı'}).getByRole('link', {name: item}).click();
  await page.getByRole('heading', {name: item, level: 1}).waitFor();
}
