import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')

for name in ['power.osm', 'water.osm']:
    path = rf"d:\new urban el\raw\{name}"
    print(f"=== {name} ===")
    tree = ET.parse(path)
    root = tree.getroot()
    nodes = root.findall('node')
    ways = root.findall('way')
    relations = root.findall('relation')
    print(f"Nodes: {len(nodes)}, Ways: {len(ways)}, Relations: {len(relations)}")
    # Sample nodes with tags
    tagged_nodes = [n for n in nodes if len(n.findall('tag')) > 0]
    print(f"Tagged nodes: {len(tagged_nodes)}")
    for n in tagged_nodes[:5]:
        tags = {t.get('k'): t.get('v') for t in n.findall('tag')}
        print(f"  Node id={n.get('id')} lat={n.get('lat')} lon={n.get('lon')} tags={tags}")
    for w in ways[:5]:
        tags = {t.get('k'): t.get('v') for t in w.findall('tag')}
        nd_refs = [nd.get('ref') for nd in w.findall('nd')]
        print(f"  Way id={w.get('id')} nds={len(nd_refs)} tags={tags}")
