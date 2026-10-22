from pathlib import Path
root=Path(__file__).resolve().parent
p=root/'dist/index.html'
s=p.read_text()
marker='const swedishMessages='
catalog=s.index(marker)
a=s.rfind('<script>',0,catalog)
b=s.index('</script>',catalog)
p.write_text(s[:a]+'<script>\n'+(root/'i18n.js').read_text()+'\n'+s[b:])
