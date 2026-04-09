# md-live

## Concept
Convenient, live wysiwyg rendering for local *.md markdown files using a shell command.

## Usage
1. In the directory to be served, execute `md-live &`, which spawns a small
   server on localhost:4000 and opens a browser tab pointing to this URL.
2. Initial webpage shows a list of files in the folder
    - User can click any file to view it
    - If it's an .md file, it renders the markdown
    - If it's an image, it shows the image (using native browser features)
    - If the user doesn't select any file, it watches the folder for changes
      and updates the list if a new file appears (e.g. if the user creates a
      .md file for editing after starting the server)
    - [for later: could render a thumbnail of files]
2. User then edits any file in the directory using their favorite editor.
    - server watches the file being displayed for changes and re-renders any
      time a file is changed.
    - server displays any inline links (e.g. images).
3. When user is finished, they can kill the job with `kill %1` or any
   equivalent. If the user closes the browser tab (so there are no more
   pages being served) the server process will close automatically.
4. For popular editors, README.me could recommend any ways to make the editor
   auto-save, so that the server would render essentially as the user types.
5. [for later: could have a mode with an editor and viewer side by side, with
   vim bindings]

## Principles
1. Very simple to use
2. No frills, no extra features just because we can
3. Require as little as possible from the user (no refreshes, etc.)
4. Allow the user to use their preferred editor or other tools
