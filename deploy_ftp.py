#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zet de gebouwde pagina via FTPS op medicatieadvies.nl.

Overgenomen uit de preferentiebeleid-repo; daar zit alle kennis over deze
hosting in (TLS-sessie hergebruiken op het datakanaal, een certificaat dat op
een andere naam staat). Alleen de doelbestanden en de mapcontrole verschillen.

Instellingen komen uit omgevingsvariabelen, of uit een bestand `.env` naast dit
script (dat bestand hoort NIET in git — zie .gitignore):

    FTP_HOST=ftp.medicatieadvies.nl
    FTP_USER=...
    FTP_PASS=...
    FTP_DIR=/

Optioneel:
    FTP_CERT_HOST=...   naam waarop het TLS-certificaat van de hoster staat, als die
                        afwijkt van FTP_HOST (shared hosting gebruikt vaak de servernaam)
    FTP_INSECURE_TLS=1  wel versleutelen, maar het certificaat niet controleren
                        (laatste redmiddel; gebruik liever FTP_CERT_HOST)

Gebruik:  python3 deploy_ftp.py [--dry-run] [--plain]
"""
import argparse, ftplib, os, socket, ssl, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))

# horizonscan.html wordt index.html op
# https://medicatieadvies.nl/horizonscan/. Dat vraagt een FTP-account met
# public_html als hoofdmap; het oorspronkelijke account van het preferentiebeleid
# is vastgezet op zijn eigen map en kan daar niet uit. Alle data zit in dat ene
# bestand.
BESTANDEN = [
    (os.path.join(BASE, 'horizonscan.html'), 'index.html'),
]

# Wordt alleen geplaatst als er nog geen .htaccess staat, zodat een eigen versie
# nooit wordt overschreven. Zorgt dat browsers de pagina na een update opnieuw ophalen.
EENMALIG = [(os.path.join(BASE, 'htaccess'), '.htaccess')]

# Nog geen restanten van eerdere versies om op te ruimen.
OPRUIMEN = []


def instellingen():
    env = {}
    pad = os.path.join(BASE, '.env')
    if os.path.exists(pad):
        for regel in open(pad, encoding='utf-8'):
            regel = regel.strip()
            if not regel or regel.startswith('#') or '=' not in regel: continue
            k, v = regel.split('=', 1)
            env[k.strip()] = v.strip().strip('"\'')
    for k in ('FTP_HOST', 'FTP_USER', 'FTP_PASS', 'FTP_DIR', 'FTP_CERT_HOST', 'FTP_INSECURE_TLS'):
        if os.environ.get(k): env[k] = os.environ[k]
    ontbreekt = [k for k in ('FTP_HOST', 'FTP_USER', 'FTP_PASS', 'FTP_DIR') if not env.get(k)]
    if ontbreekt:
        sys.exit('Ontbrekende instellingen: %s (zet ze in .env of als omgevingsvariabele)'
                 % ', '.join(ontbreekt))
    return env


def controleer_doelmap(ftp, pad):
    """Eist dat we ook echt in de bedoelde map staan.

    zorg_voor_map() valt op de inlogmap terug zodra het opgegeven pad hier niet
    bestaat. Voor een FTP-account dat op zijn doelmap is vastgezet is dat precies
    goed, maar als dit account op een andere pagina is vastgezet zou index.html
    daar terechtkomen en die pagina overschrijven. Vandaar deze controle.
    """
    delen = [d for d in (pad or '').split('/') if d]
    if not delen:
        return                                # bewust geen doelmap opgegeven
    hier = ftp.pwd().rstrip('/') or '/'
    if hier.rsplit('/', 1)[-1] != delen[-1]:
        sys.exit(
            '\nGESTOPT: er is niets geüpload.\n'
            '  gevraagd  : ...%s\n'
            '  beland in : ...%s\n'
            'Het FTP-account komt niet in de gevraagde map. Waarschijnlijk staat het vast op\n'
            'een andere map, en dan valt de mapkeuze terug op de inlogmap — precies wat we\n'
            'hier willen voorkomen. Oplossing: een FTP-account dat een map hoger begint, of\n'
            'FTP_DIR op een pad zetten dat vanaf de inlogmap klopt.'
            % (delen[-1], hier.rsplit('/', 1)[-1] or '/'))


def certificaatnamen(host, poort=21):
    """Leest uit op welke namen het certificaat van de FTP-server staat."""
    s = socket.create_connection((host, poort), timeout=30)
    s.settimeout(30)
    s.recv(2048)                       # begroeting
    s.sendall(b'AUTH TLS\r\n'); s.recv(2048)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    tls = ctx.wrap_socket(s, server_hostname=host)
    der = tls.getpeercert(binary_form=True)
    try: tls.close()
    except Exception: pass
    with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f:
        f.write(ssl.DER_cert_to_PEM_cert(der)); pad = f.name
    try:
        cert = ssl._ssl._test_decode_cert(pad)
    finally:
        os.unlink(pad)
    namen = [v for k, v in cert.get('subjectAltName', ()) if k == 'DNS']
    cn = dict(x[0] for x in cert.get('subject', ())).get('commonName')
    if cn and cn not in namen: namen.insert(0, cn)
    return namen


class FTPSHergebruik(ftplib.FTP_TLS):
    """Veel hosters (ProFTPD/LiteSpeed) eisen dat de datakanaal-TLS de sessie van de
    besturingsverbinding hergebruikt. Zonder dit volgt een '522 SSL connection failed'."""

    cert_host = None

    def auth(self):
        """Controleert het certificaat desgewenst tegen een andere naam dan de FTP-host."""
        if self.cert_host:
            echte = self.host
            self.host = self.cert_host
            try:
                return super().auth()
            finally:
                self.host = echte
        return super().auth()

    def ntransfercmd(self, cmd, rest=None):
        conn, grootte = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            sess = self.sock.session if hasattr(self.sock, 'session') else None
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=sess)
        return conn, grootte


def zorg_voor_map(ftp, pad):
    """Zoekt de doelmap op, ook als het FTP-account al in die map begint.

    Veel hosters zetten een FTP-account vast op een map ('chroot'). Na inloggen is dat
    dan '/', en bestaat het volledige pad uit het configuratiescherm niet meer. Klakkeloos
    aanmaken zou dan /preferentiebeleid/httpdocs/preferentiebeleid opleveren.
    """
    inlogmap = ftp.pwd()
    print('  inlogmap: %s' % inlogmap)
    delen = [d for d in (pad or '').split('/') if d]

    # 1. bestaat het pad zoals opgegeven, absoluut of vanaf de inlogmap?
    for kandidaat in ([pad] if (pad or '').startswith('/') else []) + (['/'.join(delen)] if delen else []):
        try:
            ftp.cwd(kandidaat)
            print('  doelmap:  %s' % ftp.pwd())
            return
        except ftplib.error_perm:
            ftp.cwd(inlogmap)

    # 2. geen pad opgegeven, of het eerste deel bestaat hier niet -> het account staat
    #    al vast op de doelmap; dan uploaden we gewoon in de inlogmap
    eerste_bestaat = False
    if delen:
        try:
            ftp.cwd(delen[0]); ftp.cwd(inlogmap); eerste_bestaat = True
        except ftplib.error_perm:
            ftp.cwd(inlogmap)
    if not eerste_bestaat:
        if delen:
            print('  let op:   %s bestaat hier niet — dit account begint kennelijk al in de '
                  'doelmap, dus we uploaden in %s' % ('/' + delen[0], inlogmap))
        print('  doelmap:  %s' % inlogmap)
        return

    # 3. het pad hoort hier wel thuis maar bestaat nog niet: aanmaken
    for deel in delen:
        try:
            ftp.cwd(deel)
        except ftplib.error_perm:
            ftp.mkd(deel); ftp.cwd(deel)
            print('  map aangemaakt: %s' % deel)
    print('  doelmap:  %s' % ftp.pwd())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='alleen tonen wat er zou gebeuren')
    ap.add_argument('--plain', action='store_true', help='onversleuteld FTP (alleen als FTPS faalt)')
    args = ap.parse_args()
    cfg = instellingen()

    teuploaden = [(l, r) for l, r in BESTANDEN if os.path.exists(l)]
    if not teuploaden:
        sys.exit('Niets te uploaden — draai eerst: python3 bijwerken.py')
    for lok, ext in teuploaden:
        print('%-46s -> %s/%s  (%.0f kB)' % (os.path.basename(lok), cfg['FTP_DIR'], ext,
                                             os.path.getsize(lok) / 1024))
    if args.dry_run:
        print('\n--dry-run: er is niets verstuurd'); return

    if args.plain:
        ftp = ftplib.FTP(cfg['FTP_HOST'], timeout=60)
        ftp.login(cfg['FTP_USER'], cfg['FTP_PASS'])
        print('\nVerbonden (onversleuteld) met %s' % cfg['FTP_HOST'])
    else:
        ctx = ssl.create_default_context()
        if cfg.get('FTP_INSECURE_TLS') == '1':
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            print('\nLET OP: het certificaat wordt niet gecontroleerd (FTP_INSECURE_TLS=1)')
        ftp = FTPSHergebruik(context=ctx, timeout=60)
        ftp.cert_host = cfg.get('FTP_CERT_HOST')
        try:
            ftp.connect(cfg['FTP_HOST'], 21)
            ftp.login(cfg['FTP_USER'], cfg['FTP_PASS'])
        except ssl.SSLCertVerificationError as e:
            print('\nHet TLS-certificaat van de FTP-server hoort niet bij "%s".' % cfg['FTP_HOST'])
            try:
                namen = certificaatnamen(cfg['FTP_HOST'])
                print('Het certificaat is geldig voor: %s' % ', '.join(namen))
                bruikbaar = [n for n in namen if not n.startswith('*')]
                print('\nOplossing: zet FTP_HOST op %s,' % (bruikbaar[0] if bruikbaar else namen[0]))
                print('of laat FTP_HOST staan en zet FTP_CERT_HOST op die naam.')
            except Exception as f:
                print('Uitlezen van het certificaat lukte niet: %s' % f)
            print('\nOorspronkelijke melding: %s' % e)
            sys.exit(1)
        ftp.prot_p()
        print('\nVerbonden (FTPS) met %s%s' % (cfg['FTP_HOST'],
              ' — certificaat gecontroleerd op %s' % cfg['FTP_CERT_HOST'] if cfg.get('FTP_CERT_HOST') else ''))
    try:
        zorg_voor_map(ftp, cfg['FTP_DIR'])
        controleer_doelmap(ftp, cfg['FTP_DIR'])
        for oud in OPRUIMEN:
            try:
                ftp.delete(oud)
                print('  verwijderd: %s (hoort hier niet meer)' % oud)
            except ftplib.error_perm:
                pass          # stond er niet, prima
        for lok, ext in EENMALIG:
            if not os.path.exists(lok): continue
            try:
                ftp.size(ext)
                print('  %s staat er al, ongemoeid gelaten' % ext)
                continue
            except Exception:
                pass
            with open(lok, 'rb') as f:
                ftp.storbinary('STOR ' + ext, f)
            print('  geplaatst: %s (browsers halen de pagina voortaan opnieuw op)' % ext)
        for lok, ext in teuploaden:
            tijdelijk = ext + '.upload'
            with open(lok, 'rb') as f:
                ftp.storbinary('STOR ' + tijdelijk, f, blocksize=1 << 16)
            try:
                ftp.delete(ext)
            except ftplib.error_perm:
                pass
            ftp.rename(tijdelijk, ext)
            print('  geplaatst: %s' % ext)
    finally:
        try: ftp.quit()
        except Exception: ftp.close()
    print('Klaar.')


if __name__ == '__main__':
    main()
