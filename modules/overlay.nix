{ lib, ... }:
{
  nixpkgs.overlays = [
    (import ../overlay.nix)
  ];
}