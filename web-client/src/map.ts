// The map: a deck.gl view with its controls, and nothing under the data (no tiles, so nothing is
// asked of another site). What is drawn comes from layers.ts.
import { Deck, MapView, type Layer } from "@deck.gl/core";

import { fitView, type Inset } from "./view";

export function createMap(parent: HTMLDivElement, onZoom: (zoom: number) => void) {
  // The size of the screen decides the first view: the whole country, tilted about 40°.
  const view = fitView(parent.clientWidth, parent.clientHeight);
  const deck = new Deck({
    parent,
    views: new MapView({ repeat: false }),
    initialViewState: view,
    controller: true,
    layers: [],
    onViewStateChange: ({ viewState }) => onZoom(viewState.zoom),
    getCursor: ({ isHovering, isDragging }) => (isDragging ? "grabbing" : isHovering ? "pointer" : "grab"),
  });
  return {
    initialZoom: view.zoom,
    setLayers: (layers: Layer[]) => deck.setProps({ layers }),
    // The map is centred in the part of the screen that the panel leaves free.
    setInset: (padding: Inset) => deck.setProps({ views: new MapView({ repeat: false, padding }) }),
  };
}
