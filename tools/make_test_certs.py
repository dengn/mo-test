#!/usr/bin/env python3
import argparse,ipaddress
from pathlib import Path
from datetime import datetime,timedelta,timezone
from cryptography import x509
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();p=a.output;p.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc);cas={}
def write(name,key,cert):
 k=p/(name+'.key')
 if k.exists():raise SystemExit('Refusing to overwrite '+str(k))
 k.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()));k.chmod(0o600)
 (p/(name+'.crt')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
for name in ['ca','badca']:
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048);subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'MO Local Test '+name)])
 cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=3)).not_valid_after(now+timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True,path_length=1),True).sign(key,hashes.SHA256());write(name,key,cert);cas[name]=(key,cert)
for name,ca,expired in [('server','ca',False),('client','ca',False),('badclient','badca',False),('expiredclient','ca',True)]:
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048);ck,cc=cas[ca]
 b=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost' if name=='server' else name)])).issuer_name(cc.subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2)).not_valid_after(now-timedelta(hours=1) if expired else now+timedelta(days=1)).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if name=='server' else ExtendedKeyUsageOID.CLIENT_AUTH]),False)
 if name=='server':b=b.add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
 write(name,key,b.sign(ck,hashes.SHA256()))
print('Generated synthetic local certificates in',p)
