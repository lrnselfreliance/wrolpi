// The 3D previews render the real loaders against the installed three.  Only the WebGL renderer is
// faked (jsdom has no WebGL); parsing, meshing and framing all run, and the dimensions line is
// only shown once a model has been loaded.
import React from 'react';
import {act, screen, waitFor} from '@testing-library/react';
import {renderWithProviders} from '../test-utils';
import {STLPreviewModal, ThreeMFPreviewModal} from './FilePreview';
import {zipSync} from 'three/examples/jsm/libs/fflate.module.js';

jest.mock('three', () => {
    const actual = jest.requireActual('three');

    class FakeWebGLRenderer {
        constructor() {
            this.domElement = global.document.createElement('canvas');
        }

        setClearColor() {
        }

        setPixelRatio() {
        }

        setSize() {
        }

        render() {
        }

        dispose() {
        }
    }

    return {...actual, WebGLRenderer: FakeWebGLRenderer};
});

// One right triangle, legs of 2 along X and 1 along Y.
const ASCII_STL = `solid ASCII
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 2 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid
`;

function binaryStl() {
    // 80-byte header, uint32 triangle count, then one 50-byte triangle: normal, three vertices.
    const buffer = new ArrayBuffer(84 + 50);
    const view = new DataView(buffer);
    view.setUint32(80, 1, true);
    const floats = [0, 0, 1, 0, 0, 0, 2, 0, 0, 0, 1, 0];
    floats.forEach((value, i) => view.setFloat32(84 + i * 4, value, true));
    return buffer;
}

function threeMF() {
    const model = `<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/>
          <vertex x="2" y="0" z="0"/>
          <vertex x="0" y="1" z="0"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2"/>
        </triangles>
      </mesh>
    </object>
  </resources>
  <build>
    <item objectid="1"/>
  </build>
</model>`;
    const rels = `<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0"
    Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>`;
    // Copy into this realm's Uint8Array: fflate tells files from folders with `instanceof`, and
    // Node's TextEncoder returns a Uint8Array from another realm than jsdom's.
    const bytes = (text) => Uint8Array.from(new TextEncoder().encode(text));
    const zipped = zipSync({'_rels/.rels': bytes(rels), '3D/3dmodel.model': bytes(model)});
    return zipped.buffer.slice(zipped.byteOffset, zipped.byteOffset + zipped.byteLength);
}

function serve(body) {
    const bytes = typeof body === 'string' ? new TextEncoder().encode(body).buffer : body;
    global.fetch = jest.fn(async () => ({
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: new Headers(),
        arrayBuffer: async () => bytes,
    }));
}

beforeEach(() => {
    global.ResizeObserver = class {
        observe() {
        }

        disconnect() {
        }
    };
});

afterEach(() => {
    delete global.fetch;
});

async function expectTriangleDimensions() {
    // The triangle spans 2 x 1 x 0; its bounding radius is half the box diagonal.
    await waitFor(() => expect(screen.getByText(/Width:/)).toBeInTheDocument(), {timeout: 5000});
    const line = screen.getByText(/Width:/).closest('div').textContent;
    expect(line).toContain('Width: 2.00');
    expect(line).toContain('Height: 1.00');
    expect(line).toContain('Length: 0.00');
    expect(line).toContain('Bounding Radius: 1.12');
}

describe('STL preview', () => {
    it('loads an ASCII STL file', async () => {
        serve(ASCII_STL);
        await act(async () => renderWithProviders(<STLPreviewModal previewFile={{path: 'models/part.stl'}}/>));
        await expectTriangleDimensions();
        // three's FileLoader fetches a Request.
        expect(global.fetch.mock.calls[0][0].url).toContain('/media/models/part.stl');
    });

    it('loads a binary STL file', async () => {
        serve(binaryStl());
        await act(async () => renderWithProviders(<STLPreviewModal previewFile={{path: 'models/part.stl'}}/>));
        await expectTriangleDimensions();
    });
});

describe('3MF preview', () => {
    it('loads a 3MF file', async () => {
        serve(threeMF());
        await act(async () => renderWithProviders(<ThreeMFPreviewModal previewFile={{path: 'models/part.3mf'}}/>));
        await expectTriangleDimensions();
    });
});
