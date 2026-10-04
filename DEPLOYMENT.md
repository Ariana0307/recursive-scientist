# Prepared deployment

The deliverable is a standalone Node server. It serves its own recorded evidence and requires no private workstation, SSH or model service. A static-only upload is not equivalent to this tested build.

Suggested compatible target: a **Render Free Web Service**, with the repository root containing `render.yaml`. Render's [Node deployment guide](https://render.com/docs/deploy-node-express-app) supports custom build/start commands. The prepared Blueprint uses root directory `website`, `npm ci && npm run build`, and `npm start`; automatic redeploy is disabled. See the [Blueprint reference](https://render.com/docs/blueprint-spec).

Expected compute cost is $0 on the Free instance. Render documents 750 free instance hours per workspace/month, idle suspension after 15 minutes, and about one minute to wake. Bandwidth/build limits also apply; without a payment method, exceeding those limits suspends service/builds rather than charging. See [Free instance limits](https://render.com/docs/free). This is a demo-hosting suggestion, not a paid production recommendation.

After the repository owner authorizes publication and resolves project rights/license status: sign into [Render Dashboard](https://dashboard.render.com/), connect GitHub with access restricted to this repository, choose New → Web Service, select the prepared release branch, set root `website`, the commands above and the Free instance type. Keep automatic deploy disabled. Do not attach a paid plan, database, disk or custom portfolio domain. Review the configuration before the first deployment. A real live URL can only be reported after a successful deployment.

Read-only checks found an accessible Sites account but no Recursive Scientist project. Sites requires Workers-compatible server output; this release's standalone Node build is not directly compatible without another adaptation. Existing unrelated Sites projects were not modified. No verified Render account connection was available in the local tools inspected. No hosting service, paid resource or public URL was created by this preparation.
