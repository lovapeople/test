# SharkNinja AU – Weekly Snapshot (auto-updating)

Every Monday morning GitHub pulls last week's data from Salesforce (same filters as the
"Weekly Snapshot SharkAU" report), rebuilds the dashboard and republishes it.
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
4. **Test:** Actions → *SharkNinja weekly snapshot* → Run workflow. The log shows the week's
   totals (for WE 27 Sep 2026: 88 shifts, 581 units, $268,721.69). Open the link to check.

## Good to know
- Only Harvey Norman and The Good Guys shifts are included (e.g. a Bing Lee shift is left out and
  listed in the run log). Change `RETAILERS` in `build.py` if that should change.
- To redo a past week, Run workflow and enter the Sunday date (e.g. `2026-09-27`).
- GitHub pauses scheduled workflows after 60 days with no repo activity; if you get that email,
  re-enable it in the Actions tab.
- The password screen only hides the page; anyone with the link can still read the data in the page source.
