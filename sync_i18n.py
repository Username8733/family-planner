from pathlib import Path
root=Path(__file__).resolve().parent
p=root/'dist/index.html'
s=p.read_text()
a=s.index('<script>\nconst englishMessages=')
b=s.index('</script>',a)
p.write_text(s[:a]+'<script>\n'+(root/'i18n.js').read_text()+'\n'+s[b:])
