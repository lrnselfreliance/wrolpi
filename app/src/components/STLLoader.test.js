// react-stl-viewer parses STL files with three-stdlib's STLLoader against our top-level three.
// Both STL encodings must parse with the installed three/three-stdlib pair.
import {STLLoader} from 'three-stdlib/loaders/STLLoader.js';

const ASCII_STL = `solid ASCII
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid
`;

function binaryStl() {
    // 80-byte header, uint32 triangle count, then one 50-byte triangle.
    const buffer = new ArrayBuffer(84 + 50);
    const view = new DataView(buffer);
    view.setUint32(80, 1, true);
    const floats = [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0];
    floats.forEach((value, i) => view.setFloat32(84 + i * 4, value, true));
    return buffer;
}

describe('STLLoader', () => {
    it('parses an ASCII STL file', () => {
        const buffer = new TextEncoder().encode(ASCII_STL).buffer;
        const geometry = new STLLoader().parse(buffer);
        expect(geometry.getAttribute('position').count).toBe(3);
        expect(Array.from(geometry.getAttribute('position').array))
            .toEqual([0, 0, 0, 1, 0, 0, 0, 1, 0]);
    });

    it('parses a binary STL file', () => {
        const geometry = new STLLoader().parse(binaryStl());
        expect(geometry.getAttribute('position').count).toBe(3);
        expect(Array.from(geometry.getAttribute('position').array))
            .toEqual([0, 0, 0, 1, 0, 0, 0, 1, 0]);
    });
});
