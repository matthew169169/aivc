# Free cloud deployment

The application can run entirely on a cloud VM: one HTTPS website serves the
workbench and its Python computations. The browser uses the same origin instead
of a separate Render API. Nothing needs to run on your personal computer.

## What is ready and what needs your account

The repository includes a Docker image, Compose stack, HTTPS gateway, persistent
data volume, background job queue, backup/update scripts, and cloud-init setup.
GitHub CI builds and smoke-tests the image on both x86 and ARM, including a real
FBA solve and a container restart that retains the uploaded model and results.

A VM cannot be activated until you create and verify your Oracle Cloud account.
You must complete Oracle's identity/card verification and accept its terms.
Creating an account alone does not migrate the current public website. After the
VM is available, its IP/hostname is needed to complete and verify the deployment.

## Free-tier boundaries

Use Oracle's **Always Free** resources, not a paid shape funded by trial credits.
The current allowance for an Always Free tenancy is up to **2 OCPUs and 12 GB of
memory** for Ampere A1, with **200 GB total block storage** across the account.
A single Ubuntu 24.04 ARM VM with 2 OCPUs, 12 GB RAM and a 50 GB boot volume fits
these published limits if there are no other allocations using them. Confirm the
Always Free eligibility and the account's actual quota before provisioning.

Oracle can lack free capacity and can reclaim idle instances. This deployment
provides no paid service or uptime guarantee. The scripts do not create resources,
upgrade an account, purchase a domain, attach paid storage or keep an idle VM busy
artificially. Keep backups outside the VM as well.

Official references:

- [Oracle Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Account verification, capacity and free-tier FAQ](https://www.oracle.com/cloud/free/faq/)
- [Standard GitHub runner availability](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

## Provision once

In Oracle's console, create an Always Free eligible `VM.Standard.A1.Flex` instance
with Ubuntu 24.04 and the sizes above. Save your SSH key. Paste
`deploy/cloud-init.yaml` into the instance's cloud-init field before creation.
Allow inbound TCP ports 80 and 443 for the website and SSH port 22 from your own
IP in the VM's network rules. The application port 8765 stays internal to Docker.
Do not enable paid resources to work around a capacity error.

Point a hostname you control at the public IP. A no-purchase option is an
IP-based hostname from [sslip.io](https://sslip.io/), for example
`203-0-113-10.sslip.io` for the documentation IP `203.0.113.10`; replace this with
the VM's real public IP. This depends on that community DNS service's availability.
Caddy obtains and renews HTTPS certificates automatically once DNS and ports work.

## Activate on the cloud VM

These commands run through SSH on the cloud VM. Cloud-init already installs the
prerequisites and clones the repository to `/opt/aivc`.

```bash
cd /opt/aivc
sudo docker build -t aivc:cloud .
sudo docker run --rm -it --entrypoint python aivc:cloud tools/cloud_credentials.py
sudo cp deploy/cloud.env.example deploy/cloud.env
sudo chmod 600 deploy/cloud.env
sudo nano deploy/cloud.env
```

Set `STUDIO_DOMAIN` to the hostname and `STUDIO_ORIGIN` to `https://` plus that
hostname. Copy the generated password-hash and session-secret assignments into
`deploy/cloud.env`, preserving their single quotes. The password prompt does not
echo or store the plaintext password. The hash contains dollar signs, so keep its
single quotes to prevent Compose variable interpolation.

```bash
sudo bash deploy/update.sh
```

Open `https://YOUR_HOSTNAME`. Login uses the configured workbench password. The
health endpoint remains public for monitoring. Confirm health reports
`job_mode: background`, that the three examples appear, and that an uploaded toy
model can run FBA and download its results. `OMICS_GEM_VERSION` reports the built
Git revision for deployment verification.

The source on GitHub and its public Pages demonstration remain available. Once
the cloud site has passed verification, its hostname can replace the demonstration
link and the old Render service can be retired. No cutover occurs automatically
before the new VM has been verified.

## Data, jobs and updates

The named `studio-data` volume stores `/data`, including run packages, uploads,
curation workspaces, job status/log files, workspace selection, projects and
external-tool settings. Bundled examples are copied into a fresh data volume
once. Existing files are preserved on later application builds and restarts.
Caches and application source are replaceable. `docker compose down` preserves
named volumes; **do not use `down -v`** if you need to keep your data.

One worker executes up to eight admitted jobs (one running, the others queued).
The API stays responsive during computation, and the browser polls job status.
A second job for the same run is rejected while the first is active. Workspace
switching and archiving an active run are also rejected until its work finishes.

A server restart interrupts unfinished computations. On startup their persisted
records become failed with an explicit restart explanation. Review partial
outputs and resubmit; the queue does not silently replay an archive operation or
claim an interrupted calculation completed. The deployment uses one API process;
multiple workers/replicas would require a shared durable job broker.

To update on the VM:

```bash
cd /opt/aivc
sudo git pull --ff-only
sudo bash deploy/backup.sh
sudo bash deploy/update.sh
```

`update.sh` builds from the public source for the VM's architecture, starts the
stack, checks health, and preserves the volume. No container-registry account is
required. Wait for active jobs to finish before updating. A backup stops the app
while copying data for consistency and restarts it when finished.

Backups are written to `deploy/backups/` with restricted permissions. Copy them
off the VM through SSH. To restore a backup on an initialized stack, stop the app,
then stream the archive into its data volume:

```bash
sudo docker compose --env-file deploy/cloud.env stop studio
sudo docker compose --env-file deploy/cloud.env run --rm --no-deps -T \
  --entrypoint tar studio -C /data -xzf - < deploy/backups/YOUR_BACKUP.tar.gz
sudo docker compose --env-file deploy/cloud.env up -d --wait
```

Restore only into an empty/new data volume, or take a backup of current data
first: restoration can overwrite files.

## Scientific capabilities

The cloud image installs the API, COBRA/GLPK and spreadsheet dependencies. Tested
workflows include uploads/imports, Atlas staging and curation, model generation,
FBA/pFBA, comparisons, maps/SAMMI session export, reports and ML profile exports.
Solver infeasibility remains a scientific result rather than a successful growth
prediction.

External MATLAB/GECKO/RAVEN, TROPPO, pyTFA databases, MEMOTE, DLKcat and deep-learning
runtimes are separate integrations. Their package/export controls remain usable,
but actual external execution requires those dependencies, compatible inputs and
any applicable licenses. A free VM does not provide a MATLAB license or prove an
external analysis completed. Settings reports the available and missing runtimes.
