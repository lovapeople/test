# SharkNinja AU – Weekly Snapshot (auto-updating)

Every minute a watcher (`watch-salesforce.yml`) pulls this month's data from Salesforce (same
filters as the "Weekly Snapshot SharkAU" report) and, if anything changed — e.g. staff adding
sales or hours, even for past weeks — republishes the dashboard within about a minute.
A backup run also checks every 30 minutes.
An open dashboard checks for new data every minute and updates in place (filters are kept);
the **⟳ Refresh** button checks straight away.
"This month" means every Mon–Sun week that ends in the month, including the week in progress,
e.g. September 2026 = WE 6, 13, 20 and 27 Sep (31 Aug – 27 Sep). Until a new month's first
shifts arrive, the previous month stays on screen. Use the **Week** filter to look at single weeks.
The link never changes: `https://<github-username>.github.io/<repo-name>/`

The dashboard keeps your existing design, logo and password screen.

## One-time setup

1. **Salesforce app login (admin):** create a Connected App (or External Client App) with
   OAuth scope "api", **Enable Client Credentials Flow** ticked, and a read-only **Run As** user
   that can see Timesheets and Product Sales. Copy the Consumer Key and Secret.
2. **GitHub:** create a repository and upload all these files, including the `.github` folder.
   Then **Settings → Pages → Source: GitHub Actions**.
3. **Secrets** (Settings → Secrets and variables → Actions):
   - `SF_INSTANCE_URL` = `https://meshcircle.my.salesforce.com`
   - `SF_CLIENT_ID` = Consumer Key
   - `SF_CLIENT_SECRET` = Consumer Secret
4. **Test:** Actions → *SharkNinja weekly snapshot* → Run workflow. The log shows each week's
   totals and the month total. Open the link to check.

## Good to know
- Only Harvey Norman and The Good Guys shifts are included (e.g. a Bing Lee shift is left out and
  listed in the run log). Change `RETAILERS` in `build.py` if that should change.
- To rebuild a past month, Run workflow and enter the last Sunday you want included (e.g. `2026-08-30` for August).
- GitHub pauses scheduled workflows after 60 days with no repo activity; if you get that email,
  re-enable it in the Actions tab. Scheduled runs can start a few minutes late when GitHub is busy.
- The password screen only hides the page; anyone with the link can still read the data in the page source.
