# Live demo, 60 to 90 seconds

Recorded on the Mac 48 with `demo/record_live.sh start` (screen, face in the bottom-left corner, microphone).
Before pressing start, have these open: the scope page at http://127.0.0.1:8798 in one window, a Terminal in
`~/CODELocalProjects/partial` with the venv active in another. Say the words below, type the commands below.
One take is fine. If a line goes wrong, pause two seconds and say it again; the cut removes the first try.

Decide this first: the agent run on Muse Spark takes up to nine minutes. Either run it before recording
(option B, the safe one) or cut the recording while it runs and resume at the end (option A). The shot list
assumes B. For A, replace shot 4 with "I'll start it and we come back", stop the recording, run
`record_live.sh start` again when it finishes.

Before recording, with the electrodes on and the board linked:

```
cd ~/CODELocalProjects/partial && source .venv/bin/activate && set -a && source .env && set +a
./demo/real_session.sh            # copies the newest block, damages it, runs the agent, scores it
```

Note the folder it prints, `examples/real-run-<stamp>/`, and the session paths `data/real-<stamp>` and
`data/real-<stamp>-damaged`. Those are what shots 3 to 5 show.

## Shot 1, 0:00 to 0:12. The scope page, your face, one clench.

Screen: the scope page, all eight traces, your face in the corner.

Say: "Four electrodes on my face, a Cerelog board, 250 samples a second. This is channel one, the chin."

Do: clench your jaw once, hard, for a second. Point at the ch1 trace as it jumps.

Say: "That spike is a clench. Every session like this is saved as raw bytes, straight off the serial port."

## Shot 2, 0:12 to 0:22. What a session folder is.

Switch to the Terminal.

Type:

```
ls ~/CODELocalProjects/silent-speech-cerelog/data/sat/*_sat-b1 | tail -8
```

Say: "A session is a tape of raw packets, a metadata file, a cue log that says which trial started when,
and a read log that ties the laptop clock to the board clock. The tape is useless without the other three,
and those are what rot: notes get lost, logs get cut, bytes get corrupted."

## Shot 3, 0:22 to 0:34. Damage it.

Type (use your real stamp):

```
cat data/real-<stamp>-damaged.damage.json
```

Say: "So I damaged a copy of the block I recorded today. Metadata deleted, most of the cue log cut, the
read log gone, a chunk cut out of the tape and forty bytes garbled."

## Shot 4, 0:34 to 0:52. The agent rebuilds it.

Type:

```
cat examples/real-run-<stamp>/reconstruction.json | head -40
```

Say: "An agent on Meta's Muse Spark gets that folder and eight small tools: list, read, hex dump, byte
histogram, find bytes, write a file, run Python. It works out the packet format from the bytes, writes its
own parser, and recovers the sample rate, the usable channels and whatever labels are left. Every claim
says observed or inferred, with the evidence and a confidence."

Scroll to one `observed` claim and one `inferred` claim and point at each.

Then show the figure:

```
open examples/real-run-<stamp>/overview.png
```

Say: "This is its own plot of my face, from a tape it had never seen a spec for."

## Shot 5, 0:52 to 1:10. The score.

Type:

```
partial score data/real-<stamp>-damaged --truth data/real-<stamp>
```

Say: "A held-out oracle, the real driver, scores it. Packets recovered, samples byte-identical, the format
claims, the rate, the labels. A wrong label marked observed costs double. That is the behavioural evidence
the track asks for."

Read the TOTAL line out loud, whatever it is.

## Shot 6, 1:10 to 1:20. One line to end on.

Face to camera.

Say: "Observed versus inferred is the whole point. The agent is allowed to not know. It is not allowed to
make things up. Repo is public, link below."

Stop: `./demo/record_live.sh stop`. The file is `demo/live-<stamp>.mp4`. Check it plays, then upload it
to Cap and paste the link into the submission form's video field.

## If something is off

- No spike on the clench: the chin pad is not over the muscle. Press it, or move it 1 cm toward the lip.
- `real_session.sh` says no real block: the 12-trial recording has not run yet. Run it first.
- The agent stopped at max steps with a low score: that is a result too. Say what it got and what it missed.
