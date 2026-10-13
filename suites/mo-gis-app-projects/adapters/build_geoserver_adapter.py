"""Compile and package the application-only GeoTools SPI from auditable source."""
from pathlib import Path
import os
import shutil
import subprocess
import zipfile
P=Path(__file__).resolve().parents[1]
home=Path(os.getenv('GEOSERVER_HOME',str(P/'projects/geoserver')))
libs=home/'webapps/geoserver/WEB-INF/lib'
build=P/'adapters/java-build';build.mkdir(parents=True,exist_ok=True)
source=P/'adapters/java/local/gis/MatrixOneDataStoreFactory.java'
classpath=os.pathsep.join(str(j) for j in sorted(libs.glob('*.jar')) if j.name!='matrixone-geotools-test-adapter.jar')
assert classpath,'Install GeoServer with its official MySQL plugin first'
compiler=[shutil.which('javac')] if shutil.which('javac') else ['java','-m','jdk.compiler/com.sun.tools.javac.Main']
subprocess.run(compiler+['-classpath',classpath,'-d',str(build),str(source)],check=True)
spi=build/'META-INF/services/org.geotools.api.data.DataStoreFactorySpi'
spi.parent.mkdir(parents=True,exist_ok=True);spi.write_text('local.gis.MatrixOneDataStoreFactory\n')
jar=P/'adapters/matrixone-geotools-test-adapter.jar'
with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(build.rglob('*')):
        if f.is_file():z.write(f,f.relative_to(build))
shutil.copy2(jar,libs/jar.name)
print('Installed',jar.name,'into owned GeoServer; restart it to discover the SPI')
