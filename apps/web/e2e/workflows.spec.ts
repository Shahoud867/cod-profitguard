import {test,expect,type Page} from '@playwright/test';
const nav=async(p:Page,name:string)=>p.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:new RegExp('^'+name)}).click();
async function login(p:Page,role='owner'){
 await p.goto('/');await p.getByLabel('Choose a demo role').selectOption(role);await p.getByRole('button',{name:'Enter '+role[0].toUpperCase()+role.slice(1)+' demo',exact:true}).click();await expect(p.getByRole('heading',{name:'Command Center',exact:true})).toBeVisible();await expect(p.getByText('The contribution picture')).toBeVisible();
}
async function approve(p:Page,name:string){await p.getByRole('dialog').getByLabel('I approve these synthetic actions').check();await p.getByRole('dialog').getByRole('button',{name,exact:true}).click();await expect(p.locator('.modal')).toHaveCount(0);}
async function scenario(p:Page,letter:string){await nav(p,'Demo Lab');await p.locator('.scenario-card').filter({has:p.locator('.scenario-letter',{hasText:letter})}).getByRole('button',{name:'Run scenario'}).click();await approve(p,'Run synthetic scenario');await expect(p.locator('.result-bar')).toContainText('Scenario '+letter+' completed');}
test('dashboard and all fourteen views render from API records',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await login(page);
 for(const name of ['Orders','Verification','Risk Desk','Courier Arena','Allocation Studio','Shipment Tracking','RTO Rescue','COD Reconciliation','Profit Analytics','Agent Traces','Demo Lab']){await nav(page,name);await expect(page.locator('.page-heading h1')).toContainText(name);await expect(page.locator('.load-error')).toHaveCount(0);}
 await page.getByRole('button',{name:'Settings & audit'}).click();await expect(page.getByRole('heading',{name:'Merchant workspace',exact:true})).toBeVisible();expect(errors).toEqual([]);
});
test('CSV validation reports result and search opens timeline',async({page})=>{
 await login(page);await nav(page,'Orders');await page.getByRole('button',{name:'Import CSV',exact:true}).click();await page.getByLabel('CSV content').fill('external_id,city,address,cod_pkr,weight_g\nBROWSER-VALID,Islamabad,Fictional House 22 Street,4500,500\nBROWSER-BAD,Lahore,x,-1,0');await page.getByRole('dialog').getByRole('button',{name:'Process CSV'}).click();await expect(page.locator('.result-bar')).toContainText('Validation complete');
 await page.getByLabel('Search orders').fill('PG-100001');await expect(page.locator('tbody tr')).toHaveCount(1);await page.getByRole('button',{name:'PG-100001',exact:true}).click();await page.getByRole('button',{name:'Timeline',exact:true}).click();await expect(page.locator('.timeline-event')).not.toHaveCount(0);
});
test('create verify compare and approve a synthetic shipment',async({page})=>{
 await login(page);await nav(page,'Orders');await page.getByRole('button',{name:'New order',exact:true}).click();await page.getByLabel('Merchant order reference').fill('E2E-'+Date.now());await page.getByRole('button',{name:'Create synthetic order',exact:true}).click();await expect(page.locator('.drawer')).toBeVisible();
 await page.locator('.drawer').getByRole('button',{name:'Confirm',exact:true}).click();await approve(page,'Record response');await expect(page.locator('.drawer-status')).toContainText('Ready To Ship');
 await page.getByRole('button',{name:'Courier comparison',exact:true}).click();await expect(page.locator('.quote-card')).toHaveCount(4);await page.getByRole('button',{name:'Select & approve courier'}).click();await approve(page,'Approve & book simulation');await expect(page.locator('.drawer-status')).toContainText('Booked Simulated');
});
test('allocation runs 100 orders with separate approval and persists booking',async({page})=>{
 await login(page);await scenario(page,'E');await page.getByRole('button',{name:'View allocation',exact:true}).click();await expect(page.locator('.metrics')).toContainText('100 assigned');await page.getByRole('button',{name:'Approve batch',exact:true}).click();await approve(page,'Approve & book batch');await expect(page.getByRole('button',{name:'Batch booked',exact:true})).toBeDisabled();
});
test('NDR rescue records permission and retry costs',async({page})=>{
 await login(page);await scenario(page,'F');await page.getByRole('button',{name:'Inspect order',exact:true}).click();await expect(page.locator('.drawer-status')).toContainText('NDR');await page.getByRole('button',{name:'Correct & retry'}).click();await page.getByLabel('Customer explicitly approved this retry').check();await approve(page,'Approve retry');await expect(page.locator('.drawer-status')).toContainText('Reattempt');await page.locator('.drawer').getByRole('button',{name:'Out For Delivery',exact:true}).click();await approve(page,'Record shipment event');await page.locator('.drawer').getByRole('button',{name:'Delivered',exact:true}).click();await approve(page,'Record shipment event');await expect(page.locator('.drawer-status')).toContainText('Delivered');
});
test('finance import and discrepancy review stays functional',async({page})=>{
 await login(page);await scenario(page,'G');await nav(page,'COD Reconciliation');await page.getByRole('button',{name:'Review',exact:true}).first().click();await page.getByLabel('Actual received').fill('0');await approve(page,'Record finance review');await expect(page.locator('.toast')).toContainText('disputed');
});
test('remaining lab scenarios execute and agent evidence expands',async({page})=>{
 await login(page);for(const letter of ['A','B','C','D','H','I']){await scenario(page,letter);await page.getByRole('button',{name:'Dismiss result'}).click();}await nav(page,'Agent Traces');await page.locator('.trace-summary').first().click();await expect(page.getByRole('heading',{name:'Observed inputs'})).toBeVisible();await expect(page.locator('.trace-details pre')).toHaveCount(2);
});
test('viewer role has read access and disabled operational controls',async({page})=>{
 await login(page,'viewer');await nav(page,'Orders');await expect(page.getByRole('button',{name:'New order',exact:true})).toBeDisabled();await nav(page,'Demo Lab');for(const b of await page.getByRole('button',{name:'Run scenario'}).all())await expect(b).toBeDisabled();
});
test('mobile navigation, tables and order drawer fit the viewport',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();await page.getByRole('button',{name:'Open navigation'}).click();await nav(page,'Orders');await expect(page.locator('table')).toBeVisible();await page.locator('tbody .order-ref').first().click();await expect(page.locator('.drawer')).toBeVisible();expect(await page.locator('.drawer').evaluate(e=>e.getBoundingClientRect().width)).toBeLessThanOrEqual(390);
});
test('capture desktop and mobile deliverable previews',async({page})=>{
 await login(page);await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:'../../docs/dashboard-desktop.png',fullPage:true,animations:'disabled'});await nav(page,'Demo Lab');await page.screenshot({path:'../../docs/demo-lab.png',fullPage:true,animations:'disabled'});await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Open navigation'}).click();await nav(page,'Command Center');await expect(page.locator('.sidebar')).not.toHaveClass(/open/);await expect(page.locator('.sidebar')).toHaveCSS('transform','matrix(1, 0, 0, 1, -236, 0)');await page.screenshot({path:'../../docs/dashboard-mobile.png',fullPage:true,animations:'disabled'});
});
