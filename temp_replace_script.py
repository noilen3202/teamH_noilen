import os

file_path = r"C:\Users\a_oohara\Downloads\teamH_noilen-master (3)\teamH_noilen-master\server.py"

old_content = """@app.route('/staff/user/user_invite', methods=['GET', 'POST'])
def staff_user_invite():
    """
    職員がボランティアユーザーを招待するページを表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))

    # GETリクエストの場合、フォームをレンダリング
    if request.method == 'GET':
        return render_template('staff/user/user_invite.html')

    # POSTリクエストの場合、フォームデータを処理
    elif request.method == 'POST':
        # フォームからデータを取得
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        mynumber = request.form.get('mynumber') # マイナンバーを追加

        # 必須フィールドのチェック
        if not all([full_name, email, mynumber]):
            flash("氏名、メールアドレス、マイナンバーは必須です。", "error")
            return render_template('staff/user/user_invite.html',
                                   full_name=full_name, email=email,
                                   phone_number=phone_number, mynumber=mynumber)

        # マイナンバーの形式チェック（12桁の数字）
        if not (mynumber.isdigit() and len(mynumber) == 12):
            flash("マイナンバーは12桁の数字で入力してください。", "error")
            return render_template('staff/user/user_invite.html',
                                   full_name=full_name, email=email,
                                   phone_number=phone_number, mynumber=mynumber)

        # セッションに一時的にデータを保存して確認画面へ
        session['invite_data'] = {
            'full_name': full_name,
            'email': email,
            'phone_number': phone_number,
            'mynumber': mynumber
        }
        return redirect(url_for('staff_user_invite_confirm'))"""

new_content = """@app.route('/staff/user/user_invite', methods=['GET', 'POST'])
def staff_user_invite():
    """
    職員がボランティアユーザーを招待するページを表示します。
    """
    # Temporarily return a string to test if the route is hit
    return "Route /staff/user/user_invite is working!"
    # Original code (commented out for testing):
    # if not check_org_login():
    #     return redirect(url_for('staff_login'))

    # # GETリクエストの場合、フォームをレンダリング
    # if request.method == 'GET':
    # #     return render_template('staff/user/user_invite.html')

    # # POSTリクエストの場合、フォームデータを処理
    # elif request.method == 'POST':
    # #     # フォームからデータを取得
    # #     full_name = request.form.get('full_name')
    # #     email = request.form.get('email')
    # #     phone_number = request.form.get('phone_number')
    # #     mynumber = request.form.get('mynumber') # マイナンバーを追加

    # #     # 必須フィールドのチェック
    # #     if not all([full_name, email, mynumber]):
    # #         flash("氏名、メールアドレス、マイナンバーは必須です。", "error")
    # #         return render_template('staff/user/user_invite.html',
    # #                                full_name=full_name, email=email,
    # #                                phone_number=phone_number, mynumber=mynumber)

    # #     # マイナンバーの形式チェック（12桁の数字）
    # #     if not (mynumber.isdigit() and len(mynumber) == 12):
    # #         flash("マイナンバーは12桁の数字で入力してください。", "error")
    # #         return render_template('staff/user/user_invite.html',
    # #                                full_name=full_name, email=email,
    # #                                phone_number=phone_number, mynumber=mynumber)

    # #     # セッションに一時的にデータを保存して確認画面へ
    # #     session['invite_data'] = {
    # #         'full_name': full_name,
    # #         'email': email,
    # #         'phone_number': phone_number,
    # #         'mynumber': mynumber
    # #     }
    # #     return redirect(url_for('staff_user_invite_confirm'))"""

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

if old_content in content:
    content = content.replace(old_content, new_content)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replacement successful.")
else:
    print("Old content not found. No replacement made.")
