"""Bounded Apple device-tree codec used by host preparation and replay tools."""
import struct


def decode(data):
    def parse(pos, depth=0):
        assert depth < 64 and pos+8 <= len(data)
        count, children = struct.unpack_from('<II', data, pos)
        pos += 8
        assert count < 512 and children < 512
        props = {}
        for _ in range(count):
            assert pos+36 <= len(data)
            name, size = struct.unpack_from('<32sI', data, pos)
            pos += 36
            assert pos+size <= len(data)
            name = name.rstrip(b'\0').decode()
            assert name not in props
            props[name] = data[pos:pos+size]
            pos += (size+3)&~3
        nodes = []
        for _ in range(children):
            pos, child = parse(pos,depth+1)
            nodes.append(child)
        return pos,(props,nodes)
    end,tree = parse(0)
    assert end==len(data) and encode(tree)==data
    return tree


def encode(tree):
    props,nodes = tree
    result = struct.pack('<II',len(props),len(nodes))
    for name,value in props.items():
        raw = name.encode()
        assert len(raw)<32
        result += struct.pack('<32sI',raw,len(value))+value+bytes(-len(value)%4)
    return result+b''.join(encode(child) for child in nodes)


def lookup(tree,*path):
    for name in path:
        tree = next(child for child in tree[1] if child[0]['name']==name.encode()+b'\0')
    return tree[0]
