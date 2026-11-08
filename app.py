from flask import Flask,render_template,request,redirect,jsonify
app =Flask(__name__)
tasks=[]#in memory for now ;database comes later
@app.route("/") 
def home():
    return render_template("index.html",tasks=tasks)
@app.route("/add",methods=["post"])
def add():
    title=request.form.get("title","").strip()
    if title:
        tasks.append(title)
    return redirect("/")
@app.route("/delete/<int:i>",methods=["POST"])
def delete(i):
    if 0<=i<len(tasks):
        tasks.pop(i)
    return redirect("/")
@app.route("/health")
def health():
    return jsonify(status="ok")
if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000)
