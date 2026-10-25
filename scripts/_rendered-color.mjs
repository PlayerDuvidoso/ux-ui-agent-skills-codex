/** Browser-native CSS Color 4 conversion and alpha compositing for render gates. */
export function installRenderedColor() {
  const canvas = new OffscreenCanvas(1, 1);
  const context = canvas.getContext('2d', { willReadFrequently: true });
  globalThis.__uxRGBA = value => {
    if (!CSS.supports('color', value)) throw new Error('Unsupported rendered color: ' + value);
    context.clearRect(0, 0, 1, 1);
    context.fillStyle = value;
    context.fillRect(0, 0, 1, 1);
    const pixel = context.getImageData(0, 0, 1, 1).data;
    return [pixel[0], pixel[1], pixel[2], pixel[3] / 255];
  };
  globalThis.__uxComposite = (foreground, background) => foreground.slice(0, 3)
    .map((channel, i) => channel * foreground[3] + background[i] * (1 - foreground[3]));
  globalThis.__uxBackground = element => {
    const stack = [];
    for (let node = element; node; node = node.parentElement) {
      const color = globalThis.__uxRGBA(getComputedStyle(node).backgroundColor);
      if (color[3] > 0) stack.push(color);
      if (color[3] >= 1) break;
    }
    let background = [255, 255, 255];
    for (let i = stack.length - 1; i >= 0; i--) background = globalThis.__uxComposite(stack[i], background);
    return background;
  };
}
