# Databricks notebook source
# MAGIC %md
# MAGIC # SFTP retrieval (SE-09) — native, script-free
# MAGIC Demonstrates connecting to an SFTP server, pattern-matching dated files, and
# MAGIC pulling them into a UC Volume — with NO standalone shell script.
# MAGIC
# MAGIC Databricks Apps only route HTTP (not SFTP port 22), and serverless tasks can't
# MAGIC reliably network to each other, so a self-contained paramiko SFTP server + client
# MAGIC run in THIS task over localhost:2222 — a genuine SFTP protocol exchange over a
# MAGIC socket. The client pattern-matches `financial_aid_*.csv` and pulls to the Volume.
# MAGIC
# MAGIC Production note: retrieval would point at a real SFTP host with creds from a UC
# MAGIC secret scope; the pull logic (paramiko, orchestrated, git-versioned) is identical.

# COMMAND ----------
# MAGIC %pip install paramiko
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import os
import socket
import threading
import time
import paramiko

dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CAT = dbutils.widgets.get("catalog")
SUF = dbutils.widgets.get("schema_suffix")
# Land in a subfolder of the EXISTING `files` volume (from Phase 0). `sftp` is a folder,
# not a volume — a new volume would need a UC resource declaration.
VOL = f"/Volumes/{CAT}/landing{SUF}/files/sftp"
dbutils.fs.mkdirs(VOL)   # subfolder in a volume via dbutils.fs (FUSE os.makedirs unsupported)

USER, PW, PORT = "poc_sftp", "poc_sftp_pw", 2222
SERVE_DIR = "/tmp/sftp_root"          # local scratch — os.makedirs is fine here
os.makedirs(SERVE_DIR, exist_ok=True)

# COMMAND ----------
# MAGIC %md ## Seed several dated files onto the SFTP server's served directory
# COMMAND ----------
fa_pd = spark.table(f"{CAT}.silver{SUF}.financial_aid").limit(200).toPandas()
csv_text = fa_pd.to_csv(index=False)
DATES = ["20260728", "20260729", "20260730"]
for d in DATES:
    with open(os.path.join(SERVE_DIR, f"financial_aid_{d}.csv"), "w") as f:
        f.write(csv_text)
print("seeded dated files:", sorted(os.listdir(SERVE_DIR)))

# COMMAND ----------
# MAGIC %md ## Inline paramiko SFTP server (rooted at SERVE_DIR)
# COMMAND ----------
class _Server(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        return (paramiko.AUTH_SUCCESSFUL
                if username == USER and password == PW else paramiko.AUTH_FAILED)
    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED
    def get_allowed_auths(self, username):
        return "password"


class _RootedSFTP(paramiko.SFTPServerInterface):
    """Minimal SFTP handler rooted at SERVE_DIR — enough for listdir + get."""
    ROOT = SERVE_DIR

    def _real(self, path):
        return os.path.join(self.ROOT, os.path.basename(path.lstrip("/")))

    def list_folder(self, path):
        out = []
        for name in os.listdir(self.ROOT):
            attr = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(self.ROOT, name)))
            attr.filename = name
            out.append(attr)
        return out

    def stat(self, path):
        return paramiko.SFTPAttributes.from_stat(os.stat(self._real(path)))

    lstat = stat

    def open(self, path, flags, attr):
        real = self._real(path)
        handle = _RootedSFTP._Handle()
        handle.readfile = open(real, "rb")
        return handle

    class _Handle(paramiko.SFTPHandle):
        def read(self, offset, length):
            self.readfile.seek(offset)
            return self.readfile.read(length)
        def close(self):
            try:
                self.readfile.close()
            except Exception:
                pass


# A socketpair gives two already-connected in-process sockets — the SFTP server runs on
# one end, the client on the other. This is a genuine paramiko SFTP protocol exchange but
# needs NO TCP bind/listen/port, so it works inside the serverless sandbox (which refuses
# loopback listeners -> "Connection refused"). Production points the client at a real host.
sock_server, sock_client = socket.socketpair()

def _serve(host_key):
    t = paramiko.Transport(sock_server)
    t.add_server_key(host_key)
    t.set_subsystem_handler("sftp", paramiko.SFTPServer, _RootedSFTP)
    t.start_server(server=_Server())
    while t.is_active():
        time.sleep(0.5)

host_key = paramiko.RSAKey.generate(2048)
server_thread = threading.Thread(target=_serve, args=(host_key,), daemon=True)
server_thread.start()
time.sleep(1)
print("SFTP server started over in-process socketpair")

# COMMAND ----------
# MAGIC %md ## Client: connect over SFTP, pattern-match, pull to the UC Volume (no shell)
# COMMAND ----------
transport = paramiko.Transport(sock_client)
transport.connect(username=USER, password=PW)
sftp = paramiko.SFTPClient.from_transport(transport)

pulled = []
for name in sftp.listdir("."):
    if name.startswith("financial_aid_") and name.endswith(".csv"):   # pattern match
        sftp.getfo(name, open(f"{VOL}/{name}", "wb"))   # SFTP GET -> UC Volume
        pulled.append(name)

sftp.close()
transport.close()
print("pulled via SFTP to Volume:", sorted(pulled))
assert len(pulled) == 3, f"expected 3 pattern-matched files, got {len(pulled)}"

# COMMAND ----------
# MAGIC %md ## Verify files landed on the Volume
# COMMAND ----------
display(dbutils.fs.ls(VOL))
